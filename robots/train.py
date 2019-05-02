import os
import sys
import argparse
import time
import signal
import math
import random

# include the netbot src directory in sys.path so we can import modules from it.
robotpath = os.path.dirname(os.path.abspath(__file__))
srcpath = os.path.join(os.path.dirname(robotpath),"src") 
sys.path.insert(0,srcpath)

from netbots_log import log
from netbots_log import setLogLevel
import netbots_ipc as nbipc
import netbots_math as nbmath

robotName = "Demo: Train v1"


def play(botSocket, srvConf):
    gameNumber = 0  # The last game number bot got from the server (0 == no game has been started)

    while True:
        try:
            # Get information to determine if bot is alive (health > 0) and if a new game has started.
            getInfoReply = botSocket.sendRecvMessage({'type': 'getInfoRequest'})
        except nbipc.NetBotSocketException as e:
            # We are always allowed to make getInfoRequests, even if our health == 0. Something serious has gone wrong.
            log(str(e), "FAILURE")
            log("Is netbot server still running?")
            quit()

        if getInfoReply['health'] == 0:
            # we are dead, there is nothing we can do until we are alive again.
            continue

        if getInfoReply['gameNumber'] != gameNumber:
            # A new game has started. Record new gameNumber and reset any variables back to their initial state
            gameNumber = getInfoReply['gameNumber']
            log("Game " + str(gameNumber) + " has started. Points so far = " + str(getInfoReply['points']))

            # currentMode is the wall we are closet to. We drive along this the currentMode wall.
            # Use special mode of "start" when we don't know where we are yet.
            currentMode = "start"

            # distance from a wall to start turning (1/5 arena size)
            turnDistance = srvConf['arenaSize'] / 5

            # The last direction we requested to go in.
            requestedDirection = None

        try:
            # find out where we are. All the logic below needs this.
            getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})

            if currentMode == "start":  # this will only be run once per game.
                # Find out which wall we are closest to and set best mode from that
                choices = [
                    ('left', getLocationReply['x']),  # distance to left wall
                    ('bottom', getLocationReply['y']),  # distance to bottom wall
                    ('right', srvConf['arenaSize'] - getLocationReply['x']),  # distance to right wall
                    ('top', srvConf['arenaSize'] - getLocationReply['y'])  # distance to top wall
                    ]

                pickMode = choices[0][0]
                pickDistance = choices[0][1]
                for i in range(1, len(choices)):
                    if choices[i][1] < pickDistance:
                        pickMode = choices[i][0]
                        pickDistance = choices[i][1]

                currentMode = pickMode
                log("Mode set to " +
                    currentMode +
                    " based on x = " +
                    str(getLocationReply['x']) +
                    ", y = " +
                    str(getLocationReply['y']), "VERBOSE")

            # If we are too close to the wall we are moving towards to then switch mode so we turn.
            if currentMode == "left" and getLocationReply['y'] < turnDistance:
                # Moving along left wall and about to hit bottom wall.
                currentMode = "bottom"
                log("Mode set to " + currentMode + " based on y = " + str(getLocationReply['y']), "VERBOSE")
            elif currentMode == "bottom" and getLocationReply['x'] > srvConf['arenaSize'] - turnDistance:
                # Moving along bottom wall and about to hit right wall.
                currentMode = "right"
                log("Mode set to " + currentMode + " based on x = " + str(getLocationReply['x']), "VERBOSE")
            elif currentMode == "right" and getLocationReply['y'] > srvConf['arenaSize'] - turnDistance:
                # Moving along right wall and about to hit top wall.
                currentMode = "top"
                log("Mode set to " + currentMode + " based on y = " + str(getLocationReply['y']), "VERBOSE")
            elif currentMode == "top" and getLocationReply['x'] < turnDistance:
                # Moving along top wall and about to hit left wall.
                currentMode = "left"
                log("Mode set to " + currentMode + " based on x = " + str(getLocationReply['x']), "VERBOSE")

            if currentMode == "left":
                # closet to left wall so go down (counter clockwise around arena)
                newDirection = math.pi * 1.5
            elif currentMode == "bottom":
                # closet to bottom wall so go right (counter clockwise around arena)
                newDirection = 0
            elif currentMode == "right":
                # closet to right wall so go up (counter clockwise around arena)
                newDirection = math.pi * 0.5
            elif currentMode == "top":
                # closet to top wall so go left (counter clockwise around arena)
                newDirection = math.pi

            if newDirection != requestedDirection:
                # Turn in a new direction
                botSocket.sendRecvMessage({'type': 'setDirectionRequest', 'requestedDirection': newDirection})
                requestedDirection = newDirection

            # Request we start accelerating to 50 speed. That should be fast enough to get
            # shot less but still slow enough to make tight turns without hitting walls.
            # Need to keep sending speed msgs in case we hit things and stop.
            botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': 50})

        except nbipc.NetBotSocketException as e:
            # Consider this a warning here. It may simply be that a request returned
            # an Error reply because our health == 0 since we last checked. We can
            # continue until the next game starts.
            log(str(e), "WARNING")
            continue

##################################################################
# Standard stuff below.
##################################################################


def quit(signal=None, frame=None):
    global botSocket
    log(botSocket.getStats())
    log("Quiting", "INFO")
    exit()


def main():
    global botSocket  # This is global so quit() can print stats in botSocket
    global robotName

    parser = argparse.ArgumentParser(formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    parser.add_argument('-ip', metavar='My IP', dest='myIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='My IP Address')
    parser.add_argument('-p', metavar='My Port', dest='myPort', type=int, nargs='?',
                        default=20010, help='My port number')
    parser.add_argument('-sip', metavar='Server IP', dest='serverIP', type=nbipc.argParseCheckIPFormat, nargs='?',
                        default='127.0.0.1', help='Server IP Address')
    parser.add_argument('-sp', metavar='Server Port', dest='serverPort', type=int, nargs='?',
                        default=20000, help='Server port number')
    parser.add_argument('-debug', dest='debug', action='store_true',
                        default=False, help='Print DEBUG level log messages.')
    parser.add_argument('-verbose', dest='verbose', action='store_true',
                        default=False, help='Print VERBOSE level log messages. Note, -debug includes -verbose.')
    args = parser.parse_args()
    setLogLevel(args.debug, args.verbose)

    try:
        botSocket = nbipc.NetBotSocket(args.myIP, args.myPort, args.serverIP, args.serverPort)
        joinReply = botSocket.sendRecvMessage({'type': 'joinRequest', 'name': robotName})
    except nbipc.NetBotSocketException as e:
        log("Is netbot server running at" + args.serverIP + ":" + str(args.serverPort) + "?")
        log(str(e), "FAILURE")
        quit()

    log("Join server was successful. We are ready to play!")

    # the server configuration tells us all about how big the arena is and other useful stuff.
    srvConf = joinReply['conf']
    log(str(srvConf), "VERBOSE")

    # Now we can play, but we may have to wait for a game to start.
    play(botSocket, srvConf)


if __name__ == "__main__":
    # execute only if run as a script
    signal.signal(signal.SIGINT, quit)
    main()
