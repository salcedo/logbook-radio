import re
import time

import falcon
import musicpd
import youtube_dl

from redis import Redis
from rq import Queue


def get_mpd():
    cli = musicpd.MPDClient()
    cli.connect(host='mpd')

    return cli


def url_is_valid(url):
    if len(url) == 0:
        return False

    if re.match(
        r'^(https?\:\/\/)?(www\.)?(youtube\.com|youtu\.?be)\/.+$',
            url) is not None:
        return True

    return False


def extract_info(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'noplaylist': True,
            'call_home': False,
            'no_color': True,
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            result = ydl.extract_info(url, download=False)
    except youtube_dl.utils.YoutubeDLError:
        raise

    return result


def filename_to_url(name):
    return 'https://www.youtube.com/watch?v={id}'.format(
        id=name.split('.')[0])


def sanitize_track_info(track):
    if track['file'] == 'stationid.mp3':
        url = 'https://logbook.pw'
    else:
        url = filename_to_url(track['file'])

    return {
        'url': url,
        'id': track['file'].split('.')[0],
        'uploader': track['artist'],
        'title': track['title'],
        'date': track['date']
    }


def handle_get():
    cli = get_mpd()

    playlistinfo = cli.playlistinfo()
    current_song = cli.currentsong()
    next_song = playlistinfo[int(cli.status()['nextsong'])]
    cli.disconnect()

    queue = []
    for track in playlistinfo:
        if 'prio' in track:
            if track['prio'] != '255':
                queue.append(track)

    queue.sort(key=lambda track: int(track['prio']), reverse=True)
    sanitized_queue = []
    for track in queue:
        sanitized_queue.append(sanitize_track_info(track))

    return {
        'current_song': sanitize_track_info(current_song),
        'next_song': sanitize_track_info(next_song),
        'queue': sanitized_queue
     }


def handle_post(url):
    if not url_is_valid(url):
        raise falcon.HTTPBadRequest(
            'Missing URL',
            'A valid YouTube URL must be submitted in the request body.')

    if queue_is_processing():
        raise falcon.HTTPBadRequest(
            'Awwww shit!',
            'The jukebox is currently processing a new track.')

    if not queue_is_open():
        raise falcon.HTTPBadRequest(
            'Awwww shit!',
            "It's a party right now. Try again later.")

    try:
        result = extract_info(url)
    except youtube_dl.utils.YoutubeDLError as e:
        raise falcon.HTTPBadRequest('YoutubeDLError', str(e))

    if int(result['duration']) > 900:
        raise falcon.HTTPBadRequest(
            'Duration',
            'Duration of {title} is longer than 15 minutes.'.format(
                title=result['title']))

    if is_currently_playing(result['id']):
        raise falcon.HTTPBadRequest(
            'Exists',
            '{title} is currently playing.'.format(title=result['title']))

    if exists_in_queue(result['id']):
        raise falcon.HTTPBadRequest(
            'Exists',
            '{title} already exists in the queue.'.format(
                title=result['title']))

    if exists_in_database(result['id']):
        queue_track(result['id'])
    else:
        Queue(
            connection=Redis(host='redis')).enqueue(
                download_and_queue_track, url)

    return {
        'id': result['id'],
        'uploader': result['uploader'],
        'date': result['upload_date'],
        'title': result['title'],
        'views': result['view_count'],
        'likes': result['like_count'],
        'dislikes': result['dislike_count']
    }


def queue_is_processing():
    if Redis(host='redis').exists('processing'):
        return True

    return False


def queue_is_open():
    cli = get_mpd()

    count = 0
    for track in cli.playlistinfo():
        if 'prio' in track:
            if track['prio'] != '255':
                count = count + 1

    cli.disconnect()

    if count >= 5:
        return False

    return True


def exists_in_database(yt_id):
    exists = False

    cli = get_mpd()
    for track in cli.playlistinfo():
        if track['file'].startswith(yt_id):
            exists = True
            break

    cli.disconnect()
    return exists


def exists_in_queue(yt_id):
    exists = False

    cli = get_mpd()
    for track in cli.playlistinfo():
        if 'prio' in track and track['file'].startswith(yt_id):
            exists = True
            break

    cli.disconnect()
    return exists


def is_currently_playing(yt_id):
    playing = False

    cli = get_mpd()
    if cli.currentsong()['file'].startswith(yt_id):
        playing = True

    cli.disconnect()
    return playing


def download_track(url):
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'outtmpl': '/music/%(id)s',
            'nooverwrites': True,
            'noplaylist': True,
            'call_home': False,
            'no_color': True,
            'keepvideo': False,
            'postprocessors': [
                {
                    'key': 'FFmpegExtractAudio'
                },
                {
                    'key': 'FFmpegMetadata'
                }
            ]
        }

        with youtube_dl.YoutubeDL(ydl_opts) as ydl:
            yt_id = ydl.extract_info(url)['id']
    except youtube_dl.utils.YoutubeDLError:
        return None

    return yt_id


def queue_track(yt_id):
    cli = get_mpd()

    # Add track to the queue
    for file in cli.listfiles():
        if file['file'].startswith(yt_id):
            while True:
                try:
                    cli.add(file['file'])
                    break
                except musicpd.CommandError:
                    time.sleep(1)

            break

    tracks = []
    for track in cli.playlistinfo():
        if track['file'].startswith(yt_id):
            track_id = int(track['id'])

        if 'prio' in track:
            if track['prio'] != '255':
                tracks.append(track)

    tracks.sort(key=lambda track: int(track['prio']), reverse=True)

    prio = 5
    for track in tracks:
        cli.prioid(prio, int(track['id']))
        prio = prio - 1

    cli.prioid(prio, track_id)

    cli.disconnect()


def download_and_queue_track(url):
    r = Redis(host='redis')

    r.set('processing', 'true')

    yt_id = download_track(url)

    if yt_id is not None:
        queue_track(yt_id)

    r.delete('processing')
