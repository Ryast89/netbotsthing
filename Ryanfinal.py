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

robotName = "RyanBot v7"


def play(botSocket, srvConf):
    gameNumber = 0  # The last game number bot got from the server (0 == no game has been started)
    while True:
        if gameNumber == 0:
            # A new game has started. Record new gameNumber and reset any variables back to their initial state
            gameNumber = 1
            # start every new game in scan mode. No point waiting if we know we have not fired our canon yet.
            currentMode = "scan"
            
            #Define other variables
            
            startTime = time.perf_counter()
            scanSlices = 1
            scanSliceWidth = 0
            minScanSpace = 0
            maxScanSpace = math.pi * 2
            timer = 0
            currentDirection = 0
            fireStep = 0
        try:
            if currentDirection == 0:
                getLocationReply = botSocket.sendRecvMessage({'type': 'getLocationRequest'})
                centerX = srvConf['arenaSize']/2
                
                if getLocationReply['x'] <= centerX and getLocationReply['y'] <= centerX:
                    currentDirection = math.pi * 1.5
                if getLocationReply['x'] <= centerX and getLocationReply['y'] > centerX:
                    currentDirection = math.pi
                if getLocationReply['x'] > centerX and getLocationReply['y'] <= centerX:
                    currentDirection = math.pi * 2
                if getLocationReply['x'] > centerX and getLocationReply['y'] < centerX:
                    currentDirection = math.pi * 0.5
                 
            timer = timer - 1
            if timer <= 0:
                timer = 30
                currentDirection = currentDirection + math.pi*0.25
                botSocket.sendRecvMessage({'type': 'setDirectionRequest', 'requestedDirection': nbmath.normalizeAngle(currentDirection)})
                botSocket.sendRecvMessage({'type': 'setSpeedRequest', 'requestedSpeed': 80})
            if currentMode == "scanExpand":
                scanSliceWidth = math.pi * 2 / scanSlices
                scanReply = botSocket.sendRecvMessage(
                    {'type': 'scanRequest', 'startRadians': nbmath.normalizeAngle(minScanSpace), 'endRadians': nbmath.normalizeAngle(maxScanSpace)})
                if scanReply['distance'] == 0:
                    maxScanSpace = maxScanSpace + scanSliceWidth/2
                    minScanSpace = minScanSpace - scanSliceWidth/2
                    scanSlices = scanSlices/2
                else:
                    if scanSlices != 32:
                        currentMode = "scan"
                    else:
                        currentTime = time.perf_counter()
                        guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                        fireDirection = minScanSpace + scanSliceWidth / 2
                        if guessSteps > fireStep:
                            botSocket.sendRecvMessage(
                                {'type': 'fireCanonRequest', 'direction': nbmath.normalizeAngle(fireDirection), 'distance': max(scanReply['distance'], 75)})
                            currentTime =  time.perf_counter()
                            guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                            fireStep = math.ceil(max(scanReply['distance'], 75)/40) + guessSteps
                        currentMode = "scanExpand"
                
            if currentMode == "scan":
                scanSliceWidth = math.pi * 2 / scanSlices
                scanCenter = (maxScanSpace + minScanSpace) / 2
                scanReply = botSocket.sendRecvMessage(
                    {'type': 'scanRequest', 'startRadians': nbmath.normalizeAngle(minScanSpace), 'endRadians': nbmath.normalizeAngle(scanCenter)})
                if scanReply['distance'] != 0:
                    if scanSlices < 32:
                        scanSlices = scanSlices * 2
                        maxScanSpace = scanCenter
                    else:
                        # fire down the center of the slice we just scanned.
                        fireDirection = minScanSpace + scanSliceWidth / 2
                        currentTime =  time.perf_counter()
                        guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                        if guessSteps > fireStep:
                            botSocket.sendRecvMessage(
                                {'type': 'fireCanonRequest', 'direction': nbmath.normalizeAngle(fireDirection), 'distance':  max(scanReply['distance'], 75)})
                            currentTime = time.perf_counter()
                            guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                            fireStep = math.ceil(max(scanReply['distance'], 75)/40) + guessSteps
                        currentMode = "scanExpand"
                        maxScanSpace = scanCenter
                else:
                    if scanSlices < 32:
                        scanSlices = scanSlices * 2
                        minScanSpace = scanCenter
                    else:
                        # fire down the center of the slice we just scanned.
                        fireDirection = maxScanSpace - scanSliceWidth / 2
                        scanReply2 = botSocket.sendRecvMessage(
                            {'type': 'scanRequest', 'startRadians': nbmath.normalizeAngle(scanCenter), 'endRadians': nbmath.normalizeAngle(maxScanSpace)})
                        if scanReply2['distance'] == 0:
                            currentMode = "scanExpand"
                        else:
                            currentTime = time.perf_counter()
                            guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                            if guessSteps > fireStep:
                                botSocket.sendRecvMessage(
                                    {'type': 'fireCanonRequest', 'direction': nbmath.normalizeAngle(fireDirection), 'distance':  max(scanReply2['distance'], 75)})
                                currentTime = time.perf_counter()
                                guessSteps = round((currentTime - startTime) / srvConf['stepSec'])
                                fireStep = math.ceil(max(scanReply2['distance'], 75)/40) + guessSteps
                            minScanSpace = scanCenter
                            currentMode = "scanExpand"
                            
        except nbipc.NetBotSocketException as e:
            # Consider this a warning here. It may simply be that a request returned
            # an Error reply because our health == 0 since we last checked. We can
            # continue until the next game starts.
            if "health == 0" not in str(e):
                log(str(e), "WARNING")
            else:
                #health is 0. Reset all variables.
                currentMode = "scan"
                timer = 0
                currentDirection = 0
                scanSlices = 1
                scanSliceWidth = 0
                minScanSpace = 0
                maxScanSpace = math.pi * 2
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
        joinReply = botSocket.sendRecvMessage({'type': 'joinRequest', 'name': robotName}, retries=300, delay=1, delayMultiplier=1)
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
