# Pandentia's Journal

*A simple journaling app*

## Why?

Multiple reasons. Mostly because:

- I didn't trust the big journaling corporations to keep my thoughts
  safe from prying eyes (even just sysops).
- I like hosting my own services. 
- I like the thought of an open-source journaling app that everyone can
  contribute to.

## Where's the official instance hosted?

[Here](https://jrnl-pandentia.qcx.io/). Please read its terms before signing
up.

# Configuration

You'll want to create a `config.yml` file in your working directory.

This file should contain (at the very least):
```yml
# this key is vital for signing tokens, keep it safe or
# people will be able to forge tokens
secret_key: 'some secret string'  # CHANGE THIS!
``` 

Optionally, it can also contain more arguments. They are listed with their
defaults here.
```yml
# the ID-generating service requires a worker ID from 0-15
# if you have multiple workers, set this accordingly
idgen_worker_id: 0

# mongodb connection information
mongodb_uri: 'mongodb://localhost'
mongodb_db: 'journal'

# recaptcha for the login page (default is testing)
recaptcha_site: '6LeIxAcTAAAAAJcZVRqyHh71UMIEGNQ_MXjiZKhI'
recaptcha_secret: '6LeIxAcTAAAAAGG-vFI1TnRWxMZNFuojJ4WifJWe'
```

You may also wish to prepare for the upcoming settings, also listed with their
defaults:
```yml
redis_uri: 'redis://localhost/0'

postgres_uri: 'postgres://localhost'
postgres_schema: 'public'
```

# Installation

First and foremost, you're likely going to want a reverse proxy like
Caddy or NGINX. I won't cover that part of the installation here, just
be aware of it.

These proxies will also allow for much easier use of SSL.

Please insert the following headers correctly:
`Host`, `X-Real-IP`, `X-Forwarded-For`. Caddy has a proxy option called
`transparent` that will do this for you.

## Docker

The default port binding is `8080`, but this is configurable through both
the ports you choose to expose and with gunicorn arguments.

```sh
docker run \
-d --restart=unless-stopped \
-p 8080:8080 \  # depends on gunicorn arguments, default
-v=/full/path/to/your/config.yml:/app/config.yml:ro \
pandentia/journal:latest \
# [optional gunicorn arguments]
```

### Updating

I highly recommend [Watchtower](https://duckduckgo.com/?q=watchtower+docker)
for this task.

## Local

`run-gunicorn.sh` does most of the legwork for you here.

```sh
./run-gunicorn.sh  # [optional gunicorn args]
```

### Updating

`git pull` will update your instance to the newest version.

You should also restart your workers after this.
