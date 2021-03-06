# Ecrit par Christian Quest le 4/6/2016
#
# ce code est sous licence WTFPL
# dernière version disponible sur https://github.com/openeventdatabase/datasources

import requests
import sys
import json
import re
from pyproj import Proj, transform
import sqlite3

# adresse de l'API
api ='http://api.openeventdatabase.org'

# base sqlite pour suivre l'évolution des événements d'un run au suivant
sql = sqlite3.connect('sytadin.db')
db = sql.cursor()
db.execute('CREATE TABLE IF NOT EXISTS sytadin_events (id text, what text, start text, geom text, label text, stop text)')

if len(sys.argv)<=2:
  # récupération de la date dans le nom du fichier
  e_when=sys.argv[1][-21:]
  e_when=e_when[:16]+':00+02:00'
else:
  e_when=sys.argv[2]

# projections utilisées pour transformation en WGS84
s_srs = Proj(init='EPSG:27572')
t_srs = Proj(init='EPSG:4326')

with open(sys.argv[1]) as json_file:
  try:
    sytadin = json.load(json_file)
    for e in sytadin['features']:
      p=e['properties']
      if p['type']=="0":
        e_type = 'unscheduled'
        e_what = 'traffic.incident'
      if p['type']=="1":
        e_type = 'unscheduled'
        e_what = 'traffic.accident'
      if p['type']=="2":
        e_type = 'scheduled'
        e_what = 'traffic.roadwork'
      if p['type']=="3":
        e_type = 'unscheduled'
        e_what = 'traffic.closed'
        if re.search('Fermeture',p['info']) or re.search('Sur ([0-9]) voi.* \\1 voi.* ferm',p['info']):
          e_what = 'traffic.closed'
        elif re.search('Sur .* voie.* ferm',p['info']):
          e_what = 'traffic.partially_closed'
      if p['type']=="9":
        e_type = 'unscheduled'
        e_what = 'traffic.obstacle'
        if re.search('inondé',p['info']):
          if re.search('Sur ([0-9]) voi.* \\1 voi.* ferm',p['info']):
            e_what = 'traffic.closed.flood'
          else:
            e_what = 'traffic.obstacle.flood'
        elif re.search('Sur ([0-9]) voi.* \\1 voi.* ferm',p['info']):
            e_what = 'traffic.closed'

      # reprojection en WGS84
      x,y = e['geometry']['coordinates']
      lon,lat = transform(s_srs,t_srs,x,y)
      geometry=dict(type = 'Point', coordinates = [round(lon,6),round(lat,6)])

      # a-t-on un évènement en cours ?
      db.execute('SELECT * FROM sytadin_events WHERE start <= ? AND what = ? AND geom = ? AND label = ?',(e_when, e_what, json.dumps(geometry,sort_keys=True), e['properties']['info'].replace('\n','')))
      last = db.fetchone()
      if last is not None:
        # on a déjà un événement similaire en cours... on le prolonge
        geojson=json.dumps(dict(properties=dict(type = e_type, what = e_what, start = last[2], stop = e_when, source='http://sytadin.fr/', label = e['properties']['info']), geometry = geometry))
        #print("PUT: "+last[0]+" "+last[2] +">"+e_when)
        r = requests.put(api+'/event/'+last[0], data = geojson)
        db.execute("UPDATE sytadin_events SET stop = ? WHERE id = ?", (e_when, last[0]))
      else:
        geojson=json.dumps(dict(properties=dict(type = e_type, what = e_what, when = e_when, source='http://sytadin.fr/', label = e['properties']['info']), geometry = geometry))
        r = requests.post(api+'/event', data = geojson)
        event = json.loads(r.text)
        #print("POST:"+event['id'])
        db.execute("INSERT INTO sytadin_events VALUES ( ? , ? , ? , ? , ? , ? )", (event['id'], e_what, e_when, json.dumps(geometry,sort_keys=True), e['properties']['info'].replace('\n',''), e_when))

    # on supprime les événements qui n'ont plus court
    db.execute("DELETE FROM sytadin_events WHERE stop < ?", (e_when,))
    db.execute("VACUUM")

    sql.commit()
  except:
    pass

db.close()

