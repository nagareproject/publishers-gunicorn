# --
# Copyright (c) 2008-2024 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Gunicorn publisher."""

import os
import logging
import traceback
import multiprocessing
from functools import partial

from ws4py import websocket
from gunicorn import util, workers, glogging
from gunicorn.app import base
from ws4py.server import wsgiutils

from nagare.server import http_publisher

gthread_worker = util.load_class(workers.SUPPORTED_WORKERS['gthread'])
workers.SUPPORTED_WORKERS['gthread'] = 'nagare.publishers.gunicorn_publisher.Worker'


class Logger(glogging.Logger):
    def __init__(self, cfg):
        super(Logger, self).__init__(cfg)

        self.error_log = logging.getLogger(cfg.logger_name + '.worker')
        self.access_log = logging.getLogger(cfg.logger_name + '.access')

        if cfg.loglevel:
            loglevel = self.LOG_LEVELS.get(cfg.loglevel.lower(), logging.INFO)
            self.error_log.setLevel(loglevel)

    def access(self, resp, req, environ, request_time):
        if self.cfg.logaccess:
            safe_atoms = self.atoms_wrapper_class(self.atoms(resp, req, environ, request_time))

            try:
                self.access_log.info(self.cfg.access_log_format, safe_atoms, extra=safe_atoms)
            except Exception:
                self.error(traceback.format_exc())


class Cfg(object):
    def __init__(self, cfg):
        self.keepalive = 30
        self.is_ssl = cfg.is_ssl
        self.ssl_options = cfg.ssl_options


class WebSocket(workers.gthread.TConn, websocket.WebSocket):
    def __init__(self):
        pass

    def bind_to(self, conn):
        workers.gthread.TConn.__init__(self, Cfg(conn.cfg), conn.sock, conn.client, conn.server)
        websocket.WebSocket.__init__(self, conn.sock)

    def close(self):
        self.closed(None)
        super(WebSocket, self).close()


class Worker(gthread_worker):
    def handle(self, conn):
        if isinstance(conn, WebSocket):
            return conn.process(conn.sock.recv(1024)), conn
        else:
            keepalive, conn = super(Worker, self).handle(conn)
            websocket = conn.websocket
            if websocket is not None:
                del conn.websocket
                websocket.bind_to(conn)
                conn = websocket

            return keepalive, conn

    def handle_request(self, req, conn):
        keepalive = super(Worker, self).handle_request(req, conn)
        conn.websocket = req.websocket

        return keepalive


class WebSocketWSGIApplication(wsgiutils.WebSocketWSGIApplication):
    def __call__(self, environ, start_response):
        environ['ws4py.socket'] = None
        return super(WebSocketWSGIApplication, self).__call__(environ, start_response)


class GunicornPublisher(base.BaseApplication):
    def __init__(self, logger_name, logaccess, app_factory, reloader, launch_browser, services_service, **config):
        self.load = app_factory
        self.reloader = reloader
        self.launch_browser = launch_browser
        self.config = config
        self.services = services_service

        super(GunicornPublisher, self).__init__()

        self.cfg.logger_name = logger_name
        self.cfg.logaccess = logaccess

    def load_config(self):
        for k, v in self.config.items():
            self.cfg.set(k, v)

        self.cfg.set('when_ready', lambda server: self.launch_browser())
        if self.reloader is not None:
            self.cfg.set('post_worker_init', lambda worker: self.services(self.post_worker_init, self.reloader, worker))

        self.cfg.set('post_request', self.post_request)
        self.cfg.set('logger_class', 'egg:nagare-publishers-gunicorn#nagare')

    @staticmethod
    def post_request(worker, req, environ, resp):
        req.websocket = environ.get('websocket')

    @staticmethod
    def post_worker_init(reloader, worker, services_service):
        services_service.handle_reload()
        services_service(reloader.start, lambda reloader, path: os._exit(0))


class Publisher(http_publisher.Publisher):
    """The Gunicorn publisher."""

    CONFIG_SPEC = dict(
        http_publisher.Publisher.CONFIG_SPEC,
        host='string(default="127.0.0.1")',
        port='integer(default=8080)',
        worker_class='string(default="gthread")',
        logaccess='boolean(default=False)',
        loglevel='string(default="")',
    )

    CONFIG_SPEC.update(
        dict(
            (param + '(default=None)').split('/')
            for param in (
                'socket/string',
                'umask/integer',
                'backlog/integer',
                'workers/string',
                'threads/string',
                'worker_connections/integer',
                'max_requests/integer',
                'timeout/integer',
                'graceful_timeout/integer',
                'keepalive/integer',
                'limit_request_line/integer',
                'limit_request_fields/integer',
                'limit_request_field_size/integer',
                'preload/boolean',
                'chdir/string',
                'daemon/boolean',
                'pidfile/string',
                'worker_tmp_dir/string',
                'user/string',
                'group/string',
                'tmp_upload_dir/string',
                'enable_stdio_inheritance/boolean',
                'proc_name/string',
                'keyfile/string',
                'certfile/string',
                'ssl_version/integer',
                'cert_reqs/integer',
                'ca_certs/string',
                'suppress_ragged_eofs/boolean',
                'do_handshake_on_connect/boolean',
                'ciphers/string',
            )
        )
    )

    websocket_app = WebSocketWSGIApplication

    def __init__(self, name, dist, logaccess, workers, threads, **config):
        """Initialization."""
        self.logaccess = logaccess

        nb_cpus = multiprocessing.cpu_count()
        workers = eval(workers or '1', {}, {'NB_CPUS': nb_cpus})  # noqa: S307
        threads = eval(threads or ('2 * NB_CPUS' if workers == 1 else '1'), {}, {'NB_CPUS': nb_cpus})  # noqa: S307

        self.has_multi_processes = workers > 1
        self.has_multi_threads = threads > 1

        super(Publisher, self).__init__(name, dist, workers=workers, threads=threads, **config)

    @property
    def endpoint(self):
        ssl = self.plugin_config['keyfile'] and self.plugin_config['certfile']
        socket = self.plugin_config['socket']

        if socket:
            bind = 'unix:{}'.format(os.path.abspath(os.path.expanduser(socket)))
            endpoint = bind + ' -> '
        else:
            bind = '{}:{}'.format(self.plugin_config['host'], self.plugin_config['port'])
            endpoint = 'http{}://{}'.format('s' if ssl else '', bind)

        return not socket, ssl, bind, endpoint

    @staticmethod
    def monitor(reload_action):
        return 0

    @staticmethod
    def set_websocket(websocket, environ):
        environ['websocket'] = websocket

    def create_websocket(self, environ):
        environ['set_websocket'] = self.set_websocket
        return WebSocket() if environ.get('HTTP_UPGRADE', '').lower() == 'websocket' else None

    def launch_browser(self):
        pass

    def start_handle_request(self, app, environ, start_response, services_service):
        return services_service(
            super(Publisher, self).start_handle_request,
            app,
            environ,
            lambda status, headers: None if start_response.__self__.status else start_response(status, headers),
        )

    def _create_app(self, services_service):
        return lambda: partial(
            services_service, self.start_handle_request, services_service(super(Publisher, self)._create_app)
        )

    def _serve(self, app_factory, host, port, socket, services_service, reloader_service=None, **config):
        services_service(super(Publisher, self)._serve, app_factory)

        if (reloader_service is not None) and self.has_multi_processes:
            self.logger.warning("The reloader service can't be activated in multi-processes")
            reloader_service = None

        config = {
            k: v for k, v in config.items() if (k not in http_publisher.Publisher.CONFIG_SPEC) and (v is not None)
        }

        services_service(
            GunicornPublisher,
            self.logger.name,
            self.logaccess,
            app_factory,
            reloader_service,
            super(Publisher, self).launch_browser,
            bind=self.endpoint[2],
            **config,
        ).run()
