#!/usr/local/bin/python
__author__ = 'aarongary'

import argparse
from bottle import template, Bottle, request, response
import json
import os
import sys
import time
from causal_paths.src.causpaths import DirectedPaths
from gevent.pywsgi import WSGIServer
from geventwebsocket.handler import WebSocketHandler
import logs
from ndex.networkn import NdexGraph
from copy import deepcopy
from causal_paths.src.path_scoring import EdgeRanking
from causal_paths import preference_schedule_ini
from gain import hash_network

api = Bottle()

log = logs.get_logger('api')

root = os.path.dirname(os.path.dirname(os.path.realpath(__file__)))
ref_networks = {}

@api.get('/statuscheck')
def index():
    return "<b>Service is up and running</b>!"

@api.get('/ontologysub/<uuid>/query/<nodeId>')
def get_ontology_sub_id(uuid, nodeId):
    sub_id = hash_network.get_ontology_sub_network(uuid, nodeId)

    return dict(data=sub_id)

@api.post('/directedpath/query')
def find_directed_path_directed_post():
    uuid = None
    server = None
    network = None
    pref_schedule = None
    original_edge_map = None
    data = request.files.get('network_cx')
    pref = request.files.get('pref_schedule')
    query_string = dict(request.query)

    #============================
    # VERIFY FILE CAN BE PARSED
    # OR UUID WAS SUPPLIED
    #============================
    if('uuid' in query_string.keys() and len(query_string['uuid']) > 0):
        if('server' in query_string.keys() and len(query_string['server']) > 0):
            server = query_string['server']
            if("http" not in server):
                server = "http://" + query_string['server']

            uuid = query_string['uuid']

            print('Getting reference network %s from %s' % (server, uuid))
            network, original_edge_map = get_reference_network(uuid, server)
            uuid = None
        else:
            response.status = 400
            response.content_type = 'application/json'
            return json.dumps({'message': 'Server must be supplied if UUID is used'})
    else:
        if data and data.file:
            try:
                read_file = data.file.read()
                network = NdexGraph(cx=json.loads(read_file))
                original_edge_map = deepcopy(network.edge)
            except Exception as e:
                response.status = 400
                response.content_type = 'application/json'
                return json.dumps({'message': 'Network file is not valid CX/JSON. Error --> ' + e.message})
        else:
            response.status = 400
            response.content_type = 'application/json'
            return json.dumps({'message': 'Valid CX/JSON file not found and uuid not supplied.'})

    if pref and pref.file:
        try:
            read_file = pref.file.read()
            pref_schedule = json.loads(read_file)
        except Exception as e:
            response.status = 400
            response.content_type = 'application/json'
            return json.dumps({'message': 'Preference schedule is not valid CX/JSON. Error --> ' + e.message})

    #==================================
    # VERIFY SOURCE NODES ARE PRESENT
    #==================================
    if('source' in query_string.keys() and len(query_string['source']) > 0):
        source = query_string['source'].split(",")
        print('Using source: %s' % source)
    else:
        response.status = 400
        response.content_type = 'application/json'
        return json.dumps({'message': 'Missing source list in query string. Example: /query?source=EGFR&target=MAP2K1 MAP2K2&pathnum=5'})
        #raise KeyError("missing source list")

    #==================================
    # VERIFY TARGET NODES ARE PRESENT
    #==================================
    if('target' in query_string.keys() and len(query_string['target']) > 0):
        target = query_string['target'].split(",")
        print('Using target: %s' % target)
    else:
        response.status = 400
        response.content_type = 'application/json'
        return json.dumps({'message': 'Missing target list in query string. Example: /query?source=EGFR&target=MAP2K1 MAP2K2&pathnum=5'})
        #raise KeyError("missing target list")

    #=================
    # PARSE N TO INT
    #=================
    pathnum = query_string.get('pathnum')
    if(pathnum is not None):
        if pathnum.isdigit():
            pathnum = int(pathnum, 10)
        else:
            pathnum = 20
    else:
            pathnum = 20

    directedPaths = DirectedPaths()

    return_paths = None

    print('Starting directed path finding')
    if('relationtypes' in query_string.keys() and len(query_string['relationtypes']) > 0):
        relation_types = query_string['relationtypes'].split()
        return_paths = directedPaths.findDirectedPaths(network, original_edge_map, source, target, npaths=pathnum,
                                                       relation_type=relation_types, pref_schedule=pref_schedule)
    else:
        return_paths = directedPaths.findDirectedPaths(network, original_edge_map, source, target, npaths=pathnum,
                                                       pref_schedule=pref_schedule)
    directedPaths = None
    result = dict(data=return_paths)
    return result

@api.get('/getPreferenceSchedule')
def get_preference_schedule():
    edgeRanking = EdgeRanking(preference_schedule_ini)
    return_dict = edgeRanking.get_nice_preference_schedule()

    return dict(data=return_dict)

def get_reference_network(uuid, host):
    if uuid not in ref_networks:
        import os
        import pickle
        ts = time.time()
        pklname = '%s.pkl' % uuid
        if not os.path.exists(pklname):
            print('Downloading reference network graph from NDEx')
            G = NdexGraph(server=host, uuid=uuid)
            print('Dumping reference network graph into pickle')
            with open(pklname, 'wb') as fh:
                pickle.dump(G, fh)
            te = time.time()
        else:
            print('Loading reference network graph from pickle')
            with open(pklname, 'rb') as fh:
                G = pickle.load(fh)
            te = time.time()
        print('Getting network took %.2fs' % (te - ts))

        ref_networks[uuid] = G
        return G, G.edge
    else:
        print "INFO: using cached network."
        G = ref_networks[uuid]
        ts = time.time()
        print('Copying reference network graph')
        G_copy = deepcopy(G)
        te = time.time()
        print('Deep copy took %.2fs' % (te - ts))
        return G_copy, G.edge

# run the web server
def main():
    status = 0
    parser = argparse.ArgumentParser()
    parser.add_argument('port', nargs='?', type=int, help='HTTP port', default=5603)
    args = parser.parse_args()

    # Load the reference network first
    #get_reference_network('04020c47-4cfd-11e8-a4bf-0ac135e8bacf',
    #                      'http://public.ndexbio.org')
    get_reference_network('50e3dff7-133e-11e6-a039-06603eb7f303',
                          'http://public.ndexbio.org')

    print 'starting web server on port %s' % args.port
    print 'press control-c to quit'
    try:
        server = WSGIServer(('0.0.0.0', args.port), api, handler_class=WebSocketHandler)
        log.info('entering main loop')
        server.serve_forever()
    except KeyboardInterrupt:
        log.info('exiting main loop')
    except Exception as e:
        str = 'could not start web server: %s' % e
        log.error(str)
        print str
        status = 1

    log.info('exiting with status %d', status)
    return status

if __name__ == '__main__':
    sys.exit(main())
