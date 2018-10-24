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

from gunicorn.app import base
from nagare.server import http_publisher


class GunicornPublisher(base.BaseApplication):
    def __init__(self, app_factory, start_handle_request, **config):
        self.app_factory = app_factory
        self.start_handle_request = start_handle_request
        self.config = config

        super(GunicornPublisher, self).__init__()

    def load_config(self):
        for k, v in self.config.items():
            self.cfg.set(k, v)

    def load(self):
        app = self.app_factory()

        return lambda environ, start_response: self.start_handle_request(app, environ, start_response)


class Publisher(http_publisher.Publisher):
    """The Gunicorn publisher"""

    CONFIG_SPEC = dict(
        http_publisher.Publisher.CONFIG_SPEC,
        host='string(default="127.0.0.1")',
        port='integer(default=8080)',
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

    def __init__(self, name, dist, workers, threads, **config):
        """Initialization
        """
        nb_cpus = multiprocessing.cpu_count()
        workers = eval(workers or '1', {}, {'NB_CPUS': nb_cpus})
        threads = eval(threads or '1', {}, {'NB_CPUS': nb_cpus})

        self.has_multi_processes = workers > 1
        self.has_multi_threads = threads > 1

        config = {k: v for k, v in config.items() if v is not None}

        super(Publisher, self).__init__(
            name, dist,
            workers=workers, threads=threads,
            **config
        )

    def _create_app(self, services_service):
        return lambda: services_service(super(Publisher, self).create_app)

    def _serve(self, app_factory, host, port, socket=None, **config):
        bind = ('unix:' + (abspath(expanduser(socket)))) if socket else ('%s:%d' % (host, port))

        GunicornPublisher(app_factory, self.start_handle_request, bind=bind, **config).run()
