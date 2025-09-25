[2025-09-25 09:46:59 +0000] [1] [INFO] Starting gunicorn 23.0.0
[2025-09-25 09:46:59 +0000] [1] [INFO] Listening at: http://0.0.0.0:5000 (1)
[2025-09-25 09:46:59 +0000] [1] [INFO] Using worker: gevent
[2025-09-25 09:46:59 +0000] [7] [INFO] Booting worker with pid: 7
[2025-09-25 09:47:00 +0000] [7] [ERROR] Exception in worker process
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/gunicorn/arbiter.py", line 608, in spawn_worker
    worker.init_process()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/ggevent.py", line 146, in init_process
    super().init_process()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/base.py", line 135, in init_process
    self.load_wsgi()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/base.py", line 147, in load_wsgi
    self.wsgi = self.app.wsgi()
                ^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/base.py", line 66, in wsgi
    self.callable = self.load()
                    ^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 57, in load
    return self.load_wsgiapp()
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 47, in load_wsgiapp
    return util.import_app(self.app_uri)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/util.py", line 370, in import_app
    mod = importlib.import_module(module)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1074, in get_code
  File "<frozen importlib._bootstrap_external>", line 1004, in source_to_code
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/app/app.py", line 119
    log.info(f" - Site Object: {first_object = first_user.get('site', 'Onbekend')}")
                                                                                   ^
SyntaxError: f-string: expecting '}'
[2025-09-25 09:47:00 +0000] [7] [INFO] Worker exiting (pid: 7)
[2025-09-25 09:47:00 +0000] [1] [ERROR] Worker (pid:7) exited with code 3
[2025-09-25 09:47:00 +0000] [1] [ERROR] Shutting down: Master
[2025-09-25 09:47:00 +0000] [1] [ERROR] Reason: Worker failed to boot.
==> Exited with status 3
==> Common ways to troubleshoot your deploy: https://render.com/docs/troubleshooting-deploys
[2025-09-25 09:47:02 +0000] [1] [INFO] Starting gunicorn 23.0.0
[2025-09-25 09:47:02 +0000] [1] [INFO] Listening at: http://0.0.0.0:5000 (1)
[2025-09-25 09:47:02 +0000] [1] [INFO] Using worker: gevent
[2025-09-25 09:47:02 +0000] [6] [INFO] Booting worker with pid: 6
[2025-09-25 09:47:02 +0000] [6] [ERROR] Exception in worker process
Traceback (most recent call last):
  File "/usr/local/lib/python3.11/site-packages/gunicorn/arbiter.py", line 608, in spawn_worker
    worker.init_process()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/ggevent.py", line 146, in init_process
    super().init_process()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/base.py", line 135, in init_process
    self.load_wsgi()
  File "/usr/local/lib/python3.11/site-packages/gunicorn/workers/base.py", line 147, in load_wsgi
    self.wsgi = self.app.wsgi()
                ^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/base.py", line 66, in wsgi
    self.callable = self.load()
                    ^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 57, in load
    return self.load_wsgiapp()
           ^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/app/wsgiapp.py", line 47, in load_wsgiapp
    return util.import_app(self.app_uri)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/site-packages/gunicorn/util.py", line 370, in import_app
    mod = importlib.import_module(module)
          ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "/usr/local/lib/python3.11/importlib/__init__.py", line 126, in import_module
    return _bootstrap._gcd_import(name[level:], package, level)
           ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "<frozen importlib._bootstrap>", line 1204, in _gcd_import
  File "<frozen importlib._bootstrap>", line 1176, in _find_and_load
  File "<frozen importlib._bootstrap>", line 1147, in _find_and_load_unlocked
  File "<frozen importlib._bootstrap>", line 690, in _load_unlocked
  File "<frozen importlib._bootstrap_external>", line 936, in exec_module
  File "<frozen importlib._bootstrap_external>", line 1074, in get_code
  File "<frozen importlib._bootstrap_external>", line 1004, in source_to_code
  File "<frozen importlib._bootstrap>", line 241, in _call_with_frames_removed
  File "/app/app.py", line 119
    log.info(f" - Site Object: {first_object = first_user.get('site', 'Onbekend')}")
                                                                                   ^
SyntaxError: f-string: expecting '}'
[2025-09-25 09:47:02 +0000] [6] [INFO] Worker exiting (pid: 6)
[2025-09-25 09:47:03 +0000] [1] [ERROR] Worker (pid:6) exited with code 3
[2025-09-25 09:47:03 +0000] [1] [ERROR] Shutting down: Master
[2025-09-25 09:47:03 +0000] [1] [ERROR] Reason: Worker failed to boot.
