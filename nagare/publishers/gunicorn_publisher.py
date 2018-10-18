# --
# Copyright (c) 2008-2018 Net-ng.
# All rights reserved.
#
# This software is licensed under the BSD License, as described in
# the file LICENSE.txt, which you should have received as part of
# this distribution.
# --

"""The Gunicorn publisher"""

import multiprocessing
from os.path import expanduser, abspath

from gunicorn import reloader
from gunicorn.app import base
from nagare.server import http_publisher


class Reloader(object):
    def __init__(self, reloader_service, extra_files=None, callback=None):
        print('RELOADER', extra_files, callback)

    def add_extra_file(self, filename):
        print('Extra file', filename)

    def start(self):
        pass


class GunicornPublisher(base.BaseApplication):
    def __init__(self, app_factory, start_handle_request, files_to_watch, **config):
        self.app_factory = app_factory
        self.start_handle_request = start_handle_request
        self.files_to_watch = files_to_watch
        self.config = config

        super(GunicornPublisher, self).__init__()

    def load_config(self):
        for k, v in self.config.items():
            self.cfg.set(k, v)

        def add_files(worker):
            for filename in self.files_to_watch:
                worker.reloader.add_extra_file(filename)

        self.cfg.set('post_worker_init', add_files)

    def load(self):
        app = self.app_factory()
        return lambda environ, start_response: self.start_handle_request(app, environ, start_response)


class Publisher(http_publisher.Publisher):
    """The Gunicorn publisher"""

    INTERNAL_RELOADER = True
    CONFIG_SPEC = dict(
        http_publisher.Publisher.CONFIG_SPEC,
        host='string(default="127.0.0.1")',
        port='integer(default=8080)',
        reload_engine='string(default="nagare")',
        files_to_watch='string_list(default=list("$config_filename"))'
    )
    for spec in (
        'socket/string', 'umask/integer', 'backlog/integer',
        'worker_class/string', 'workers/string', 'threads/string',
        'worker_connections/integer', 'max_requests/integer',
        'timeout/integer', 'graceful_timeout/integer', 'keep_alive/integer',
        'limit_request_line/integer', 'limit_request_fields/integer',
        'limit_request_field_size/integer',
        'preload/boolean',
        'chdir/string', 'daemon/boolean', 'pidfile/string', 'worker_tmp_dir/string',
        'user/string', 'group/string',
        'tmp_upload_dir/string', 'accesslog/string', 'access_log_format/string',
        'errorlog/string', 'loglevel/string', 'logger_class/string', 'logconf/string',
        'syslog_addr/string', 'syslog/boolean', 'syslog_prefix/string', 'syslog_facility/string',
        'enable_stdio_inheritance/boolean', 'proc_name/string',
        'keyfile/string', 'certfile/string', 'ssl_version/integer', 'cert_reqs/integer',
        'ca_certs/string', 'suppress_ragged_eofs/boolean', 'do_handshake_on_connect/boolean',
        'ciphers/string'
    ):
        name, type_ = spec.split('/')
        CONFIG_SPEC[name] = type_ + '(default=None)'

    def __init__(self, name, dist, workers, threads, files_to_watch, reloader_service=None, **config):
        """Initialization
        """
        nb_cpus = multiprocessing.cpu_count()
        workers = eval(workers or '1', {}, {'NB_CPUS': nb_cpus})
        threads = eval(threads or '1', {}, {'NB_CPUS': nb_cpus})

        self.has_multi_processes = workers > 1
        self.has_multi_threads = threads > 1

        config = {k: v for k, v in config.items() if v is not None}

        nagare_reloader = lambda extra_files, callback: Reloader(reloader_service, extra_files, callback)  # noqa: E731
        reloader.reloader_engines['nagare'] = nagare_reloader
        reload = reloader_service is not None

        super(Publisher, self).__init__(
            name, dist,
            workers=workers, threads=threads,
            reload=reload,
            files_to_watch=reloader_service.files if reload else (),
            **config
        )

    def _create_app(self, services_service):
        return lambda: services_service(super(Publisher, self).create_app)

    def _serve(self, app_factory, host, port, socket=None, **config):
        bind = ('unix:' + (abspath(expanduser(socket)))) if socket else ('%s:%d' % (host, port))

        GunicornPublisher(app_factory, self.start_handle_request, bind=bind, **config).run()
