import asyncio
import aiohttp
from aiohttp import web
from aiohttp_cors import setup, ResourceOptions
import os
import json
import requests
import logging
import time
import urllib.parse
import sys


async def on_prepare(request, response):
    request.start_time = time.time()

async def on_response(request, response):
    pass

async def on_request_start(request, *args, **kwargs):
    pass

async def on_request_end(request, *args, **kwargs):
    pass


def get_query_param(request, param_name):
   if isinstance(request, aiohttp.web.Request):
       return request.rel_url.query.get(param_name)
   else:
       query_params = urllib.parse.parse_qs(request)
       param_values = query_params.get(param_name, [])
       return param_values[0] if param_values else None   


async def get_mjstyle_json(request):
   name = request.match_info['name']
   base_path = os.path.dirname(os.path.abspath(__file__))
   file_path = os.path.join(base_path, 'docs', 'mjstyle', f'{name}.json')
       
   if os.path.exists(file_path):
       with open(file_path, 'rb') as f:
           json_data = f.read()
       return web.Response(body=json_data, content_type='application/json')
   else:
       return web.Response(status=404)
   
async def get_marked_js(request):
   base_path = os.path.dirname(os.path.abspath(__file__))
   file_path = os.path.join(base_path, 'web', 'lib', 'marked.min.js')    
   
   if os.path.exists(file_path):
       with open(file_path, 'rb') as f:
           js_data = f.read()
       return web.Response(body=js_data, content_type='application/javascript')
   else:
       return web.Response(status=404)

async def get_purify_js(request):
   base_path = os.path.dirname(os.path.abspath(__file__))
   file_path = os.path.join(base_path, 'web', 'lib', 'purify.min.js')     
   
   if os.path.exists(file_path):
       with open(file_path, 'rb') as f:
           js_data = f.read()
       return web.Response(body=js_data, content_type='application/javascript')
   else:
       return web.Response(status=404)
    

def load_api_config():
   try:
       current_dir = os.path.dirname(os.path.realpath(__file__))
       config_path = os.path.join(current_dir, 'Comflyapi.json')

       if not os.path.exists(config_path):
           return {}

       with open(config_path, 'r') as f:
           config = json.load(f)
       return config
   except Exception as e:
       logging.error(f"Error loading API config: {str(e)}")
       return {}

async def get_config(request):
   config = load_api_config()
   return web.json_response(config)      
    

app = web.Application()

# Configure CORS
cors = setup(app, defaults={
   "*": ResourceOptions(
       allow_credentials=True,
       expose_headers="*",
       allow_headers="*",
       allow_methods="*",
   )
})


# Define routes
routes = [
   ("/api/get_config", get_config),
   ("/lib/marked.min.js", get_marked_js), 
   ("/lib/purify.min.js", get_purify_js),
   ("/mjstyle/{name}.json", get_mjstyle_json),
]

# Add routes to the application with CORS
for route in routes:
    resource = cors.add(app.router.add_resource(route[0]))
    cors.add(resource.add_route("GET", route[1]))
    cors.add(resource.add_route("POST", route[1]))

def start_api_server():
   logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
   web.run_app(app, port=8080, access_log=None, print=None)

if __name__ == '__main__':
   print("\033[32m ** Comfly Loaded :\033[33m Go Younjung Is My Favorite Girl!--T8star\033[0m")
   start_api_server()