# PC Distance

PC Distance permet de contrôler un ordinateur Windows depuis le navigateur d'un téléphone connecté au même réseau local.

## Fonctions

- Affichage de l'écran avec commandes tactiles
- Pavé tactile, clic gauche, clic droit et double-clic
- Clavier distant, raccourcis et saisie de texte
- Explorateur du dossier utilisateur et transferts de fichiers
- Presse-papiers
- Lancement des raccourcis du menu Démarrer
- Informations CPU, mémoire et stockage
- Contrôle du volume, verrouillage et commandes Windows rapides
- Interface de bureau en Tkinter avec adresse, code de connexion et QR code

## Démarrage depuis les sources

1. Installe Python 3.11 ou supérieur sur Windows.
2. Décompresse le projet.
3. Lance `start.bat`.
4. Le script crée l'environnement Python et installe les dépendances.
5. Sur le téléphone, ouvre l'adresse affichée dans la fenêtre PC Distance.
6. Saisis le code temporaire affiché sur le PC.
7. Clique sur **Autoriser le contrôle** dans la fenêtre PC Distance.

Les deux appareils doivent être sur le même réseau local. À la première utilisation, Windows peut demander d'autoriser l'application sur les réseaux privés.

## Créer l'installateur Windows depuis GitHub

1. Crée un dépôt GitHub vide.
2. Envoie tous les fichiers de ce dossier à la racine du dépôt.
3. Vérifie que le dépôt possède la branche `main`.
4. Ouvre l'onglet **Actions** sur GitHub.
5. Sélectionne **Build Windows Installer** puis **Run workflow**.
6. Une fois le workflow terminé, ouvre son exécution et récupère `PC-Distance-Windows-Installer` dans **Artifacts**.
7. Le ZIP téléchargé contient `PCDistance-Setup.exe`.

Le workflow installe les dépendances de construction, regroupe Python et les bibliothèques dans l'application, puis crée un installateur Windows. Les utilisateurs de l'installateur n'ont pas besoin d'installer Python séparément.

Pour publier automatiquement un fichier d'installation dans **Releases**, crée un tag commençant par `v`, par exemple `v2.0.0`, puis pousse ce tag sur GitHub.

## Sécurité

- Le serveur écoute sur le réseau local pour permettre la connexion du téléphone.
- Le code à 8 chiffres est renouvelé à chaque démarrage.
- Les tentatives de connexion sont limitées.
- Le contrôle souris/clavier est désactivé au démarrage et doit être autorisé depuis le PC.
- L'explorateur de fichiers est limité au dossier utilisateur Windows.
- Aucun terminal distant ni exécution de commande libre n'est exposé.
- N'ouvrez pas le port du serveur sur Internet et ne partagez pas le code de connexion.

## Structure

```text
PC_Distance_LAN_V2/
├── .github/workflows/build.yml
├── web/index.html
├── app.py
├── icon.ico
├── installer.iss
├── requirements.txt
├── start.bat
└── README.md
```
