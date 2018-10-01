import journal

app = journal.create_app_from_config_file()

app.debug = True
app.config['ENV'] = 'development'

app.run('0.0.0.0', 5000)
