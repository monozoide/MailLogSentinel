# MailLogSentinel - Liste des Tâches avec Cases à Cocher (Version complète)

## 🔥 **PRIORITÉ CRITIQUE**

### 🐛 Bugs bloquants
- [ ] [BUG] SQL export failed #354  
  Fichier : `lib/maillogsentinel/sql_export.py` ou `bin/maillogsentinel.py`  
  Impact : export SQL cassé  
  Effort : 2-4h
- [ ] [BUG] Could not load headers from bundled mapping for test setup #347  
  Fichier : `tests/` ou `lib/maillogsentinel/mapping.py`  
  Impact : tests cassés  
  Effort : 1-3h
- [ ] sql_export/sql_import dupliqués dans systemd setup  
  Fichier : `bin/maillogsentinel.py`  
  Impact : config corrompue  
  Effort : 1-2h

### 📚 Documentation critique
- [ ] Fix typo section `first-time-run` du README  
- [ ] FAQ liens cassés : Daily Usage et Development

---

## 🚀 **PRIORITÉ HAUTE**

- [ ] Dans log_anonymizer ajouter un avertissement RGPD :  
  > ⚠ Disclaimer : There is no guarantee this script removes all personal data. Always check results manually.
- [ ] Refactor du `mls.conf` : ajouter vérification par script principal avant exécution.
- [ ] Mettre à jour la documentation du README pour inclure le guide Debian.  
- [ ] Documenter toutes les options de `maillogsentinel.conf`.  
- [ ] Expliquer les occurrences Errno X dans les rapports email.  
- [ ] Clarifier différences entre --purge et --reset.  
- [ ] Archiver les données --reset/--purge dans dossier dédié.

---

## 📋 **PRIORITÉ MOYENNE**

- [ ] Mettre à jour la doc API dans `docs/api/`
- [ ] Réécrire `mls.conf` : meilleure organisation + descriptions par section.
- [ ] Benchmark de l’extraction (performance et vitesse).
- [ ] Créer un paquet `.deb`.
- [ ] FAQ : compatibilité bases de données (SQLite3 pour import, tous SGBDR pour export).
- [ ] FAQ : fournisseur ipinfo + backlink vers sapics/ip-location-db.
- [ ] FAQ : confidentialité, rassurer sur DB-IP offline.
- [ ] Créer page wiki 'System Requirements & Prerequisites' + lien README.
- [ ] Améliorer UI --setup (couleurs et ergonomie).
- [ ] Ajouter options config pour désactiver CSV/email.
- [ ] Ajouter détection d’erreur si mail.log mal formé.
- [ ] Vérifier infos SMTP si pas MTA.

---

## 🔧 **PRIORITÉ BASSE**

- [ ] Maintenir compatibilité avec Python/Debian (nouveaux tests CI).  
- [ ] Nettoyage intégral du code (retravail des commentaires).  
- [ ] Ajouter syntaxe timers systemd à la doc.  
- [ ] Permettre rapport local only (user local).  
- [ ] Simplifier config systemd (réduire fichiers générés).  
- [ ] Améliorer backup.  
- [ ] Clarifier relation timers/conf.  
- [ ] Améliorer templates GitHub (section Expected deliverables editable).  
- [ ] Ajouter case DCO dans templates.

---

## 🚢 **DÉVELOPPEMENT FUTUR**

- [ ] Refactor pour support `journald`.  
- [ ] Ajout télémétrie (usage/metrics optionnel).  
- [ ] Créer script d’installation automatique `tools/auto-install.sh`.  
- [ ] Créer paquets VM/Container (GH Actions, Docker Hub, LXD, Packer).

---

## 📊 **STATISTIQUES**

- Tâches totales : 36  
- Effort estimé : ~60h (7,5 jours)  
- Objectif : organisation stable et robuste avant 2026.