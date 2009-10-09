#!/bin/bash

#if [ ! -f $HOME/.mpd/mpd.pid ]; then
if [ $(pgrep -x mpd|wc -l) -lt 1 ]; then
  echo "starting mpd"
  mpd
  count=1
  while [ $(pgrep -x mpd|wc -l) -lt 1 ]; do
     count=$(($count+1))
     if [ $count -gt 5 ]; then
       echo "mpd did not start!"
       exit 1
     fi
     echo "waiting for mpd to start"
     sleep 1
  done
fi

if [ $(pgrep -x mpdscribble|wc -l) -lt 1 ]; then
  echo "starting mpdscribble"
  mpdscribble
fi

if [ $(ps -ef|grep mpd-pl-random-album.py|grep python|grep -v grep|wc -l) -lt 1 ]; then
  echo "starting mpd-pl-random-album"
  ($HOME/bin/mpd-pl-random-album.py -d >> /tmp/mpd-pl-random-album.py 2>&1) &
fi
