import requests
import numpy as np
import mercantile
import random
import threading
import concurrent.futures
import time
import tomllib

# globals for config file values initialized to placeholder/empty values
multi_threading = False
threads_per_layer = 1
hostname = ""
filename = ""
tilewidth = 256
tileheight = 256
minzoom = 4
maxzoom = 8
num_trials = 1
layers = []
epsg = 3857
limit_x = False
limit_y = False
min_x = -1
min_y = -1
max_x = -1
max_y = -1

# lock to allow for thread-safe file and stdout write
write_lock = threading.Lock()


# reads in the config file and populates the globals
def readconfig():
    global hostname
    global filename
    global multi_threading
    global threads_per_layer
    global num_trials
    global epsg
    global tilewidth
    global tileheight
    global minzoom
    global maxzoom
    global limit_y
    global limit_x
    global min_x
    global min_y
    global max_x
    global max_y

    with open("config.toml", "rb") as f:
        data = tomllib.load(f)

        server_settings = data["server_settings"]
        layers_obj = data["layers"]
        script_settings = data["script_settings"]
        tile_settings = data["tile_settings"]
        advanced = data["advanced"]

        hostname = server_settings["hostname"]
        for key, value in layers_obj.items():
            if value != '':
                layers.append(value)

        filename = script_settings["filename"]
        multi_threading = script_settings["multi_threading"]
        threads_per_layer = script_settings["threads_per_layer"]
        num_trials = script_settings["num_trials"]
        epsg = script_settings["epsg"]

        tilewidth = tile_settings["tile_width"]
        tileheight = tile_settings["tile_height"]
        minzoom = tile_settings["min_zoom"]
        maxzoom = tile_settings["max_zoom"]

        limit_x = advanced["limit_x"]
        limit_y = advanced["limit_y"]
        min_x = advanced["min_x"]
        min_y = advanced["min_y"]
        max_x = advanced["max_x"]
        max_y = advanced["max_y"]


# randomly generates the query dict for a specific request
def generatequery(layer_name):

    # generate a random zoom level
    zoomlvl = random.randint(minzoom, maxzoom)

    # generate x tile
    if limit_x:
        tile_x = random.randint(min_x * (2 ** (zoomlvl - minzoom)), max_x * (2 ** (zoomlvl - minzoom)))
    else:
        tile_x = random.randint(0, (2 ** zoomlvl) - 1)

    # generate y tile
    if limit_y:
        tile_y = random.randint(min_y * (2 ** (zoomlvl - minzoom)), max_y * (2 ** (zoomlvl - minzoom)))
    else:
        tile_y = random.randint(0, (2 ** zoomlvl) - 1)


    # generate the bounding box using mercantile
    boundingboxstr = ''
    if epsg == 3857:
        boundingbox = mercantile.xy_bounds(tile_x, tile_y, zoomlvl)
        boundingboxstr = (str(boundingbox.left) + ',' + str(boundingbox.bottom) + ',' +
                          str(boundingbox.right) + ',' + str(boundingbox.top))
    else: # catch-all else in case someone messes up specifying 4326
        boundingbox = mercantile.bounds(tile_x, tile_y, zoomlvl)

        # convert to string for url (format is west,south,east,north)
        boundingboxstr = (str(boundingbox.west) + ',' + str(boundingbox.south) + ',' +
                          str(boundingbox.east) + ',' + str(boundingbox.north))

    # the wms query. TODO a lot here is hard coded that should be changed
    query = {
        'SERVICE': 'WMS',
        'VERSION': '1.3.0',
        'REQUEST': 'GetMap',
        'LAYERS': layer_name,
        'CRS': 'EPSG:' + str(epsg),
        'STYLES': 'raster/default',
        'WIDTH': tilewidth,
        'HEIGHT': tileheight,
        'BBOX': boundingboxstr,
        'COLORSCALERANGE': '0.957,1200', # worst hard-code offender cause a lot of the tiles will look garbage
    }

    return query


def runbatchtest(layer_name, file_to_write):

    # numpy array of trial results. This allows us to calculate more complicated statistics on the trial results
    trials = np.array([])

    for x in range(num_trials):
        printout = "Batch testing layer " + layer_name + ": " + str(x + 1) + "/" + str(num_trials)
        print("\r" + printout, end="")
        start = time.perf_counter()
        response = requests.get(url=hostname, params=generatequery(layer_name))
        # check the code to ensure its 200 otherwise flood the user's terminal in a very bad way (for now)
        if response.status_code == 200:
            trials = np.append(trials, time.perf_counter() - start)
        else:
            print("error with layer " + layer_name)

    # calculate some statistics on our results
    avgtime = round((np.average(trials) * 1000), 4)
    lowerquart = round((np.percentile(trials, 25) * 1000), 4)
    upperquart = round((np.percentile(trials, 75) * 1000), 4)
    onepercentlow = round((np.percentile(trials, 1) * 1000), 4)
    onepercenthigh = round((np.percentile(trials, 99) * 1000), 4)
    totaltime = round(sum(trials) * 1000, 4)

    print("")
    file_to_write.write(layer_name + "\t" + format(totaltime) + "\t" + format(avgtime) + "\t" + format(lowerquart) + "\t" +
                        format(upperquart) + "\t" + format(onepercentlow) + "\t" + format(onepercenthigh) + "\n")

# run batch tests with multiple threads
def testing_thread(layer_name, fileToWrite):

    # numpy array of trial results. This allows us to calculate more complicated statistics on the trial results
    trials = np.array([])
    with write_lock:
        print("Thread testing " + layer_name + " started")

    for x in range(num_trials):
        start = time.perf_counter()
        response = requests.get(url=hostname, params=generatequery(layer_name))
        if response.status_code == 200:
            trials = np.append(trials, time.perf_counter() - start)
        else:
            with write_lock:
                print("error with layer " + layer_name)

    # calculate some statistics on our results
    avgtime = round((np.average(trials) * 1000), 4)
    lowerquart = round((np.percentile(trials, 25) * 1000), 4)
    upperquart = round((np.percentile(trials, 75) * 1000), 4)
    onepercentlow = round((np.percentile(trials, 1) * 1000), 4)
    onepercenthigh = round((np.percentile(trials, 99) * 1000), 4)
    totaltime = round(sum(trials) * 1000, 4)

    with write_lock:
        print("Thread testing " + layer_name + " finished")
        with open(fileToWrite, 'a') as file:
            file.write(layer_name + "\t" + format(totaltime) + "\t" + format(avgtime) + "\t" + format(lowerquart) +
                       "\t" + format(upperquart) + "\t" + format(onepercentlow) + "\t" + format(onepercenthigh) + "\n")


if __name__ == "__main__":

    # populate the globals
    readconfig()

    if multi_threading == "true":
        print("script running in multi-threaded mode\n")

        # clear file and add file headers
        with open(filename, 'w') as f:
            f.write("Layer on thread\tTotal thread execution time(ms)\tAvg request time (ms)\tLower quartile (ms)\tUpper quartile (ms)\tLower 1% (ms)\tUpper 1% (ms)\n")

        # create iterable of layers to pass to threads
        layersforthreads = []
        for x in range(threads_per_layer):
            layersforthreads = layersforthreads + layers

        # create iterable of output file name
        filenameforthreads = []
        for x in range(len(layersforthreads)):
            filenameforthreads.append(filename)

        # specify number of threads
        thread_num = len(layersforthreads)

        with concurrent.futures.ThreadPoolExecutor(max_workers=thread_num) as executor:
            executor.map(testing_thread, layersforthreads, filenameforthreads)

    else:
        print("script running in single-threaded mode\n")
        with open(filename, 'w') as f:
            f.write("Layer\tTotal time(ms)\tAvg request time (ms)\tLower quartile (ms)\tUpper quartile (ms)\tLower 1% (ms)\tUpper 1% (ms)\n")

            for layer in layers:
                runbatchtest(layer, f)

            print("Saving average file")
