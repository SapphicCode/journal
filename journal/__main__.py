import configparser

import journal

cfg = configparser.ConfigParser()
cfg.read('config.ini')

recaptcha = {
    'site': cfg.get('main', 'recaptcha_site'),
    'secret': cfg.get('main', 'recaptcha_secret'),
}

mongodb_uri = cfg.get('main', 'mongodb_uri')
mongodb_db = cfg.get('main', 'mongodb_db')

idgen_worker_id = cfg.getint('main', 'idgen_worker_id')
secret_key = cfg.get('main', 'secret_key')

app = journal.create_app(
    recaptcha=recaptcha, mongodb_uri=mongodb_uri, mongodb_db=mongodb_db, idgen_worker_id=idgen_worker_id,
    secret_key=secret_key,
)

app.debug = True
app.config['ENV'] = 'development'

app.run('0.0.0.0', 5000)
