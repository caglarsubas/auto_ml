"""Fixed local socket behind an operator-controlled buffering TLS ingress."""

bind = "unix:/run/declarai/api.sock"
workers = 1
worker_class = "sync"
threads = 1
timeout = 120
graceful_timeout = 30
# Legacy SFS/HPO still own process-local progress and cancellation flags.
# Do not silently split/recycle that state before durable migration.
max_requests = 0
max_requests_jitter = 0
backlog = 64
worker_tmp_dir = "/tmp"
umask = 0o007
reload = False
preload_app = False
control_socket_disable = True
proxy_protocol = False
# Only Django's explicitly configured canonical proxy header determines HTTPS.
# The socket/its mount is the trust boundary; do not expose a TCP listener.
secure_scheme_headers = {}
forwarded_allow_ips = ""
forwarder_headers = ""
accesslog = None
errorlog = "-"
loglevel = "warning"
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190
