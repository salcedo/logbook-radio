import os
import random
import time

from redis import Redis

from jukebox import get_mpd


mold = 0
identify = 0


def do_the_things():
    global mold
    global identify

    cli = get_mpd()

    playlistinfo = cli.playlistinfo()
    queued = []
    not_queued = []
    for track in playlistinfo:
        if 'prio' in track:
            queued.append(track)
        else:
            not_queued.append(track)

    # Nothing queued up? Let's shuffle every half hour.
    if len(queued) == 0 and mold >= 180:
        mold = 0
        cli.shuffle()
    else:
        mold = mold + 1

    # Trim the fat.
    if len(playlistinfo) > 1024:
        purge = random.choice(not_queued)

        cli.deleteid(int(purge['id']))
        os.unlink('/music/{file}'.format(file=purge['file']))

    # station id ~60 min
    if identify >= 360:
        identify = 0
        cli.add('stationid.mp3')
        for track in cli.playlistinfo():
            if track['file'] == 'stationid.mp3':
                idtrack = track
                break

        cli.prioid(255, int(idtrack['id']))
    else:
        currentsong = cli.currentsong()
        for track in cli.playlistinfo():
            if track['file'] == 'stationid.mp3' and 'prio' not in track and \
                    currentsong['file'] != 'stationid.mp3':
                cli.deleteid(int(track['id']))

        identify = identify + 1

    cli.disconnect()


def controller():
    r = Redis(host='redis')

    r.delete('processing')

    cli = get_mpd()

    cli.crossfade(5)

    cli.clear()
    cli.add('/')

    cli.random(1)
    cli.repeat(1)

    cli.play()
    cli.disconnect()

    while True:
        do_the_things()
        time.sleep(10)


if __name__ == '__main__':
    controller()
