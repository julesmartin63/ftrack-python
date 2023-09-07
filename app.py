import ftrack_api
from jinja2 import Environment, FileSystemLoader
import codecs
from flask import Flask, render_template

app = Flask(__name__, template_folder='templates')


@app.route('/')
def index():
    return render_template('template.html')


if __name__ == '__main__':
    app.run(debug=True, port=5000)

# Créez la session ftrack
session = ftrack_api.Session(
    server_url='https://emc2.ftrackapp.com',
    api_key='YTgzNTJmNWQtMGI1Ny00MmU0LTgyNjktYWE3Mzc0MjJkMjg5Ojo3YzRmM2EyZC00OWQ5LTQzMjItOWExOS1hN2UzNmRmMTEzOTg',
    api_user='martin@zap.team'
)

# Liste de clés
types = session.types.keys()

# Chemin vers le répertoire contenant le modèle HTML
template_dir = "./templates"
# Créez un environnement Jinja2
env = Environment(loader=FileSystemLoader(template_dir))

# Chargez le modèle
template = env.get_template('template.html')

# Remplir le modèle avec les données
html_content = template.render(types=types)

# Enregistrez le contenu HTML dans un fichier index.html
with codecs.open('listAllTypes.html', 'w', encoding='utf-8') as file:
    file.write(html_content)

# Confirmez que le fichier a été enregistré
print('Fichier listAllTypes.html enregistré avec succès.')
