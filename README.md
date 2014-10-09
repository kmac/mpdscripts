mpdscripts
==========

Some scripts to interact with MPD.


mpd-random-playlist-album.py
============================
A python script which plays a random album from the current MPD playlist.
It can also be run as a daemon, where at the end of an album it will select
a new album from the current playlist to play; It does this by monitoring track changes,
detecting the end of an album.

The basic idea of this script is to load up the playlist with albums,
then run this script as a daemon. When one album finishes, a new album will be chosen at random from the playlist.
Similar to Amarok's album shuffle mode or foobar2000's random album mode.


Depends: python-mpd


From the help:
```
This script picks a random album from the MPD playlist.  Called with no
args it will choose the first song from a random album on the current playlist
and start playing from that point. Obviously, this only works if the playlist
is arranged as a list of albums. It's meant to provide a rudimentary album
shuffle function for MPD.

In daemon mode the script will monitor MPD and select a new album
in the playlist after the last song on an album has ended (see -d option).

Options:
   -h|--help
   -d|--daemon  : daemon mode. Monitor MPD for track changes. At end of album select
                  a new random album from the playlist
   -D|--debug   : Print debug messages to stdout
   -p|--passive : testing only. Don't make any changes to the MPD playlist

Requires:
   python-mpd

Limitations:
   The album switching is currently triggered when the last song on an album
   is reached.  If the user changes the current song selection during
   the last song on an album then this script will kick in, randomly
   selecting a new album.  Unfortunately I don't see how to avoid this
   unless we were to time how long the last song has been playing for, and
   compare it to the song length given by MPD.
```


Examples
--------

Select a new album to play from the current playlist:
```
 ./mpd-random-playlist-album.py
```

Start a daemon, logging output to /tmp/mpd-random-playlist-album.log
```
(./mpd-random-playlist-album.py -d > /tmp/mpd-random-playlist-album.log 2>&1 ) &
```


gmusic-fetch-playlist.py
========================

A python script which retrieves .m3u playlists via GMusicProxy (https://github.com/diraimondo/gmusicproxy),
optionally loading the playlist into the current MPD playlist.
This script is basically just a helper for GMusicProxy.


From the help:
```
This script fetches playlists using GMusicProxy (https://github.com/diraimondo/gmusicproxy)
and optionally adds to current MPD playlist.

Usage
-----
Retrieve album playlist:
  gmusic-fetch-playlist.py <options> --artist 'some artist' --title 'album title'

Retrieve album playlist and add into existing MPD playlist:
  gmusic-fetch-playlist.py <options> --load --artist 'some artist' --title 'album title'

Retrieve playlist of entire collection:
  gmusic-fetch-playlist.py <options> --collection

Retrieve all playlists:
  gmusic-fetch-playlist.py <options> --playlists


<options>:
  -a|--artist: artist name
  -t|--title: album title
  -f|--force : force playlist overwriting
  -l|--load : load the playlist into currently mpd playlist using mpc
  -D : debug


Dependencies
------------
GMusicProxy
Google Music
mpc


Configuration
-------------
You may need to define a ~/.gmusicfetchrc file to override default values.

Contents of .gmusicfetchrc:

[gmusicfetch]

# the base url for the running gmusicproxy:
gmusic-proxy-url = http://localhost:9999

# the playlist directory to store generated playlists:
mpd-playlist-dir = <base mpd path>/mpd/playlists

# the playlist prefix. All files will be prefixed with this (can be left blank):
playlist-prefix = gmusic-
```
