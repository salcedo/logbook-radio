import json

import falcon

from jukebox import handle_get, handle_post


class JukeboxResource(object):
    def on_get(self, req, resp):
        resp.status = falcon.HTTP_200
        resp.body = json.dumps(handle_get())

    def on_post(self, req, resp):
        url = req.stream.read(req.content_length or 0).decode(
            'utf-8', 'ignore')

        try:
            result = handle_post(url)
        except falcon.HTTPBadRequest:
            raise

        resp.status = falcon.HTTP_201
        resp.body = json.dumps(result)


api = falcon.API()

api.add_route('/jukebox', JukeboxResource())
