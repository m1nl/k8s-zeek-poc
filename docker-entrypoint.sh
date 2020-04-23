#!/bin/sh

cleanup() {
  for s in $(ls -1 /etc/service) ; do
    exec /usr/bin/sv force-stop $s
  done

  if [ "x$RUNSVDIR_PID" != "x" ] ; then
    kill -HUP $RUNSVDIR_PID
    wait $RUNSVDIR_PID

    sleep 0.5
  fi

  exit
}

trap cleanup TERM HUP QUIT INT

exec /usr/bin/runsvdir -P /etc/service &
RUNSVDIR_PID=$!

wait $RUNSVDIR_PID

cleanup
