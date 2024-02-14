# testing script to use to text xpublish_wms. For now, only the nc datasets are supported.

import requests
import numpy as np
import mercantile
import random
import threading
import concurrent.futures
import time

# disable or enable a multi-threaded testing run (true/false). if the script is running in multi-threaded mode,
# threads_per_layer specifies how many threads are created for each data layer
multi_threading = "false"

threads_per_layer = 1

hostname = "http://localhost:9000"

# file names for the single-threaded and multi-threaded modes respectively
single_filename = ""
threaded_filename = ""

# the tile width and height used for the generated testing tiles. For now we will leave this at 256x256 since this is
# what ncWMS uses by default
tilewidth = "256"
tileheight = "256"

# specify the zoom range to use during random tile generation. note that zoom levels below 4 will not be constrained
# in latitude to the actual dataset, so for the most accurate results the minzoom should be 4 or higher
minzoom = 4
maxzoom = 8

# specify the number of trials to perform (per layer/thread). note that this will take a very long time with high
# trial numbers
numTrials = 50

# specify the testing layers here. these are the four layers we used in the previous testing
#layers = ["test1%2FWind_speed_surface",
#          "test1%2FMean_period_of_wind_waves_surface",
#          "test2%2Fssh",
#          "test2%2Fsurface_boundary_layer_thickness"]

# layers = ["wd",
#           "tmp2m"]

layers = ["ssh",
          "surface_boundary_layer_thickness"]



# lock to allow for thread-safe file and stdout write
write_lock = threading.Lock()


# generates a random tile for a given layer (using a random tile and zoom level selected from the spherical mercator system)
# returns the request URL to get that tile
def generateTile(layerName):
    # IMPORTANT: Our grib2 dataset only covers from latitude +52 to latitude -15. As a result, we will exclude generating
    # tiles that would fall completely outside this latitude range during our testing.

    # generate a random zoom level (for this testing we will limit zoom to between zoom 4 and zoom 8 because higher zoom
    # levels are unrealistic with our data resolution)
    zoomlvl = random.randint(minzoom, maxzoom)

    # generate random tile number n for x (lon). here we will take the zoom level squared as n+1 and select from 0-n
    tile_x = random.randint(0, (2 ** zoomlvl) - 1)

    if zoomlvl > 3:
        # generate random tile number n for y (lat). This is more complex because we need to restrict to our latitude limits.
        # for zoom level 4, we want to limit to tiles 5-8. for zoom level 5, this would turn into tiles 10-16, and so on.
        # as a result, we will multiply 5 and 8 by 2^n to get our limits, where n is the number of zoom levels above 4.
        tile_y = random.randint(5 * (2 ** (zoomlvl - 4)), 8 * (2 ** (zoomlvl - 4)))
    else:
        # if the zoom level happens to be under 4, ignore the above rules
        tile_y = random.randint(0, (2 ** zoomlvl) - 1)


    # generate the bounding box using mercantile
    boundingbox = mercantile.bounds(tile_x, tile_y, zoomlvl)

    # convert to string for url (format is west,south,east,north)
    boundingboxstr = (str(boundingbox.west) + ',' + str(boundingbox.south) + ',' +
                      str(boundingbox.east) + ',' + str(boundingbox.north))
    # this is the 'template' request url that the randomTile function will complete to generate a random tile
    # the hostname, layer name, and bounding box are added dynamically for each request
    # the 'TIME' parameter is omitted from the URL since the datasets we are testing are valid only at a single time
    tileurl = (hostname + "/wms/?FORMAT=image%2Fpng&TRANSPARENT=TRUE&STYLES=default-scalar%2Fdefault&LAYERS=" +
                layerName + "&COLORSCALERANGE=-1.082%2C24.48&NUMCOLORBANDS=250&ABOVEMAXCOLOR=0x000000" +
                            "&BELOWMINCOLOR=0x000000&BGCOLOR=transparent&LOGSCALE=false&SERVICE=WMS&VERSION=1.1.1" +
                            "&REQUEST=GetMap&SRS=EPSG%3A3857&BBOX=" +
                boundingboxstr + "&WIDTH=" + tilewidth + "&HEIGHT=" + tileheight)

    return tileurl

def runBatchTest(layerName, fileToWrite):

    # numpy array of trial results. This allows us to calculate more complicated statistics on the trial results
    trials = np.array([])

    for x in range(numTrials):
        printout = "Batch testing layer " + layerName + ": " + str(x+1) + "/" + str(numTrials)
        print("\r" + printout, end="")
        start = time.perf_counter()
        response = requests.get(url=generateTile(layerName))
        trials = np.append(trials, time.perf_counter() - start)

    # calculate some statistics on our results
    avgtime = round((np.average(trials) * 1000), 4)
    lowerquart = round((np.percentile(trials, 25) * 1000), 4)
    upperquart = round((np.percentile(trials, 75) * 1000), 4)
    onepercentlow = round((np.percentile(trials, 1) * 1000), 4)
    onepercenthigh = round((np.percentile(trials, 99) * 1000), 4)
    totaltime = round(sum(trials) * 1000, 4)

    print("")
    fileToWrite.write(layerName + "\t" + format(totaltime) + "\t" + format(avgtime) + "\t" + format(lowerquart) + "\t" +
                      format(upperquart) + "\t" + format(onepercentlow) + "\t" + format(onepercenthigh) + "\n")

# run batch tests with multiple threads
def testingThread(layerName, fileToWrite):

    # numpy array of trial results. This allows us to calculate more complicated statistics on the trial results
    trials = np.array([])
    with write_lock:
        print("Thread testing " + layerName + " started")

    for x in range(numTrials):
        start = time.perf_counter()
        response = requests.get(url=generateTile(layerName))
        trials = np.append(trials, time.perf_counter() - start)

    # calculate some statistics on our results
    avgtime = round((np.average(trials) * 1000), 4)
    lowerquart = round((np.percentile(trials, 25) * 1000), 4)
    upperquart = round((np.percentile(trials, 75) * 1000), 4)
    onepercentlow = round((np.percentile(trials, 1) * 1000), 4)
    onepercenthigh = round((np.percentile(trials, 99) * 1000), 4)
    totaltime = round(sum(trials) * 1000, 4)

    with write_lock:
        print("Thread testing " + layerName + " finished")
        with open(fileToWrite, 'a') as file:
            file.write(layerName + "\t" + format(totaltime) + "\t" + format(avgtime) + "\t" + format(lowerquart) +
                       "\t" + format(upperquart) + "\t" + format(onepercentlow) + "\t" + format(onepercenthigh) + "\n")


if __name__ == "__main__":
    if multi_threading == "true":
        print("script running in multi-threaded mode\n")

        # clear file and add file headers
        with open(threaded_filename, 'w') as f:
            f.write("Layer\tTotal time(ms)\tAvg time (ms)\tLower quartile (ms)\tUpper quartile (ms)\tLower 1% (ms)\tUpper 1% (ms)\n")

        # create iterable of layers to pass to threads
        layersforthreads = []
        for x in range(threads_per_layer):
            layersforthreads = layersforthreads + layers

        # create iterable of output file name
        filenameforthreads = []
        for x in range(len(layersforthreads)):
            filenameforthreads.append(threaded_filename)

        # specify number of threads
        thread_num = len(layersforthreads)

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_num) as executor:
            executor.map(testingThread, layersforthreads, filenameforthreads)

    else:
        print("script running in single-threaded mode\n")
        with open(single_filename, 'w') as f:
            f.write("Layer\tTotal time(ms)\tAvg time (ms)\tLower quartile (ms)\tUpper quartile (ms)\tLower 1% (ms)\tUpper 1% (ms)\n")

            for layer in layers:
                runBatchTest(layer, f)

            print("Saving average file")
