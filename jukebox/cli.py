import os
import sys

from musicpd import MPDClient


def usage():
    print('usage: {} <ls|rm> [id]'.format(sys.argv[0]))


def main():
    if len(sys.argv) < 2:
        usage()
        return

    cli = MPDClient()
    cli.connect(host='mpd')

    if sys.argv[1] == 'ls':
        for track in cli.playlistinfo():
            print('{id}: ({file}) {artist} - {title}'.format(
                id=track['id'], file=track['file'], artist=track['artist'],
                title=track['title']))
    elif sys.argv[1] == 'rm' and len(sys.argv) == 3:
        for track in cli.playlistinfo():
            if track['id'] == sys.argv[2]:
                cli.deleteid(int(track['id']))
                os.unlink('/music/{file}'.format(file=track['file']))

                print('deleted track {id}: ({file}) {artist} - {title}'.format(
                    id=track['id'], file=track['file'], artist=track['artist'],
                    title=track['title']))

                break
    else:
        usage()


if __name__ == '__main__':
    main()
