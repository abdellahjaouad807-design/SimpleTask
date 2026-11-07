"""Base initiale : les processus les plus courants sous Windows.

Format d'une ligne :  CODE | nom | éditeur | description
  V = Vital (ne jamais fermer, risque élevé)
  f = Peut être fermé, risque faible (une fonction s'arrête jusqu'au redémarrage)
  F = Peut être fermé, aucun risque
"""

_DATA = r"""
# ---------- Cœur de Windows ----------
V|System|Microsoft|Le cœur de Windows. Sans lui, l'ordinateur s'arrête.
V|Registry|Microsoft|Garde en mémoire les réglages de Windows (le « registre »).
V|Memory Compression|Microsoft|Compresse la mémoire pour que le PC reste rapide. Sa RAM affichée est normale.
V|Secure System|Microsoft|Partie protégée de Windows qui garde les mots de passe en sécurité.
V|smss.exe|Microsoft|Démarre la session Windows au lancement du PC.
V|csrss.exe|Microsoft|Gère les fenêtres et la console. Le fermer provoque un écran bleu.
V|wininit.exe|Microsoft|Lance les services de base de Windows au démarrage.
V|winlogon.exe|Microsoft|Gère l'ouverture et la fermeture de votre session.
V|services.exe|Microsoft|Chef d'orchestre de tous les services Windows.
V|lsass.exe|Microsoft|Vérifie les mots de passe et la sécurité de la session.
V|LsaIso.exe|Microsoft|Version protégée du gardien des mots de passe.
V|svchost.exe|Microsoft|Conteneur qui fait tourner de nombreux services Windows (réseau, son, mises à jour...).
V|dwm.exe|Microsoft|Dessine toutes les fenêtres à l'écran (effets, transparence).
V|explorer.exe|Microsoft|L'explorateur : barre des tâches, bureau et dossiers.
V|fontdrvhost.exe|Microsoft|Affiche les polices de caractères.
V|sihost.exe|Microsoft|Gère des éléments de l'interface (menu Démarrer, notifications).
V|taskhostw.exe|Microsoft|Lance les tâches planifiées de Windows.
V|ctfmon.exe|Microsoft|Gère le clavier, la saisie et la langue de saisie.
V|conhost.exe|Microsoft|Fenêtre qui accompagne les programmes en ligne de commande.
V|RuntimeBroker.exe|Microsoft|Contrôle les autorisations des applications du Microsoft Store.
V|StartMenuExperienceHost.exe|Microsoft|Le menu Démarrer.
V|ShellExperienceHost.exe|Microsoft|Affiche le calendrier, le centre de notifications et d'autres panneaux.
V|SearchHost.exe|Microsoft|La recherche de la barre des tâches (Windows 11).
V|SearchApp.exe|Microsoft|La recherche de la barre des tâches (Windows 10).
V|SearchIndexer.exe|Microsoft|Indexe vos fichiers pour que la recherche soit rapide.
V|SearchProtocolHost.exe|Microsoft|Aide l'indexation des fichiers pour la recherche.
V|SearchFilterHost.exe|Microsoft|Aide l'indexation des fichiers pour la recherche.
V|spoolsv.exe|Microsoft|Gère les impressions (file d'attente de l'imprimante).
V|WmiPrvSE.exe|Microsoft|Donne des informations sur le PC aux programmes qui en demandent.
V|dllhost.exe|Microsoft|Fait tourner des morceaux de programmes Windows (miniatures, etc.).
V|audiodg.exe|Microsoft|Moteur du son de Windows. Le fermer coupe le son.
V|TextInputHost.exe|Microsoft|Clavier tactile, emojis et saisie de texte.
V|LockApp.exe|Microsoft|L'écran de verrouillage.
V|ApplicationFrameHost.exe|Microsoft|Cadre des fenêtres des applications du Microsoft Store.
V|SystemSettingsBroker.exe|Microsoft|Aide l'application Paramètres à modifier les réglages.
V|backgroundTaskHost.exe|Microsoft|Fait tourner les petites tâches de fond des applications.
V|WUDFHost.exe|Microsoft|Fait fonctionner certains pilotes (capteurs, lecteur d'empreintes, USB).
V|dasHost.exe|Microsoft|Gère les appareils connectés (Bluetooth, réseau).
V|MoUsoCoreWorker.exe|Microsoft|Windows Update : recherche et installe les mises à jour.
V|usocoreworker.exe|Microsoft|Windows Update : recherche et installe les mises à jour.
V|TiWorker.exe|Microsoft|Installe les mises à jour de Windows. Peut être gourmand un moment.
V|TrustedInstaller.exe|Microsoft|Installe les mises à jour et composants de Windows.
V|msiexec.exe|Microsoft|Installe ou désinstalle un programme. Le fermer peut casser l'installation.
V|consent.exe|Microsoft|La fenêtre « Voulez-vous autoriser cette application... ».
V|LogonUI.exe|Microsoft|L'écran de connexion de Windows.
V|userinit.exe|Microsoft|Prépare votre session à l'ouverture.
V|unsecapp.exe|Microsoft|Permet à Windows de répondre aux programmes qui demandent des informations.
V|WmiApSrv.exe|Microsoft|Service de mesure des performances de Windows.
V|CompPkgSrv.exe|Microsoft|Aide les applications du Microsoft Store à fonctionner.
V|sppsvc.exe|Microsoft|Vérifie la licence (activation) de Windows.
V|SppExtComObj.Exe|Microsoft|Aide à vérifier l'activation de Windows.
V|rundll32.exe|Microsoft|Lance des morceaux de programmes. Souvent utilisé par Windows et les pilotes.
V|smartscreen.exe|Microsoft|Protection SmartScreen : bloque les fichiers et sites dangereux.
V|SgrmBroker.exe|Microsoft|Surveille l'intégrité de Windows au démarrage (sécurité).
V|PresentationFontCache.exe|Microsoft|Accélère l'affichage des polices pour certains programmes.
V|AggregatorHost.exe|Microsoft|Collecte d'informations système utilisée par Windows.
V|wlanext.exe|Microsoft|Gère le Wi-Fi.
V|msdtc.exe|Microsoft|Coordonne des opérations entre programmes (bases de données).
V|WerFaultSecure.exe|Microsoft|Rapport d'erreur d'un programme protégé de Windows.
V|ngciso.exe|Microsoft|Protège le code PIN et Windows Hello.
V|ShellHost.exe|Microsoft|Gère des éléments de la barre des tâches (Windows 11).
V|DataExchangeHost.exe|Microsoft|Gère le glisser-déposer et le copier-coller entre applications.
V|SecurityHealthService.exe|Microsoft|Service de Sécurité Windows (état de la protection).
V|MsMpEng.exe|Microsoft|L'antivirus Microsoft Defender. Peut être gourmand pendant une analyse.
V|NisSrv.exe|Microsoft|Microsoft Defender : protection contre les attaques réseau.
V|MpDefenderCoreService.exe|Microsoft|Microsoft Defender : service principal.
V|MpCmdRun.exe|Microsoft|Microsoft Defender : analyse ou mise à jour en cours.
V|MsSense.exe|Microsoft|Microsoft Defender pour entreprise.
V|vmcompute.exe|Microsoft|Fait tourner les machines virtuelles et WSL.
V|vmmem|Microsoft|Mémoire utilisée par une machine virtuelle ou WSL.
V|vmmemWSL|Microsoft|Mémoire utilisée par WSL (Linux dans Windows).
f|SecurityHealthSystray.exe|Microsoft|Icône du bouclier Sécurité Windows près de l'horloge. La protection continue sans elle.
f|SystemSettings.exe|Microsoft|L'application Paramètres de Windows.
f|Widgets.exe|Microsoft|Le panneau Widgets (météo, actualités).
f|WidgetService.exe|Microsoft|Service des Widgets (météo, actualités).
f|PhoneExperienceHost.exe|Microsoft|Mobile connecté : relie votre téléphone au PC.
f|YourPhone.exe|Microsoft|Votre téléphone : relie votre téléphone au PC.
f|GameBar.exe|Microsoft|La Xbox Game Bar (Win + G).
f|GameBarFTServer.exe|Microsoft|Aide de la Xbox Game Bar.
f|gamingservices.exe|Microsoft|Services Xbox utilisés par les jeux du Microsoft Store et du Game Pass.
f|gamingservicesnet.exe|Microsoft|Services réseau Xbox pour les jeux.
f|SettingSyncHost.exe|Microsoft|Synchronise vos réglages Windows avec votre compte Microsoft.
f|CredentialUIBroker.exe|Microsoft|Fenêtre qui demande un mot de passe ou un code PIN.
f|PickerHost.exe|Microsoft|Fenêtre de choix de fichier ou d'application.
f|TabTip.exe|Microsoft|Clavier tactile.
f|WerFault.exe|Microsoft|Rapport d'erreur après le plantage d'un programme.
f|wermgr.exe|Microsoft|Envoi des rapports d'erreur à Microsoft.
f|CompatTelRunner.exe|Microsoft|Télémétrie : analyse la compatibilité du PC. Peut être gourmand un moment.
f|DeviceCensus.exe|Microsoft|Télémétrie : inventaire du matériel.
f|MusNotification.exe|Microsoft|Notifications de Windows Update.
f|MusNotifyIcon.exe|Microsoft|Icône de notification de Windows Update.
f|SIHClient.exe|Microsoft|Petites réparations automatiques de Windows Update.
f|UserOOBEBroker.exe|Microsoft|Écran « Terminons la configuration de votre appareil ».
f|CrossDeviceService.exe|Microsoft|Relie le PC à vos autres appareils.
f|CrossDeviceResume.exe|Microsoft|Reprendre sur le PC une activité commencée sur le téléphone.
f|WindowsPackageManagerServer.exe|Microsoft|Gestionnaire de paquets winget.
f|AppVShNotify.exe|Microsoft|Notifications des applications Office virtualisées.
f|ScreenClippingHost.exe|Microsoft|Capture d'écran (Win + Maj + S).
f|Taskmgr.exe|Microsoft|Le Gestionnaire de tâches de Windows.
f|mmc.exe|Microsoft|Console d'administration (Gestion de l'ordinateur, Services...).
f|regedit.exe|Microsoft|L'éditeur du registre de Windows.
f|cmd.exe|Microsoft|Invite de commandes. Le fermer arrête la commande en cours.
f|powershell.exe|Microsoft|PowerShell (commandes). Le fermer arrête le script en cours.
f|pwsh.exe|Microsoft|PowerShell 7 (commandes). Le fermer arrête le script en cours.
f|WindowsTerminal.exe|Microsoft|Le Terminal Windows.
f|OpenConsole.exe|Microsoft|Console utilisée par le Terminal Windows.
f|wsl.exe|Microsoft|Linux dans Windows (WSL).
f|wslhost.exe|Microsoft|Linux dans Windows (WSL).
f|wslservice.exe|Microsoft|Service de Linux dans Windows (WSL).
F|notepad.exe|Microsoft|Le Bloc-notes. Pensez à enregistrer avant de fermer.
F|mspaint.exe|Microsoft|Paint.
F|CalculatorApp.exe|Microsoft|La Calculatrice.
F|Calculator.exe|Microsoft|La Calculatrice.
F|SnippingTool.exe|Microsoft|Outil Capture d'écran.
F|Photos.exe|Microsoft|L'application Photos.
F|Microsoft.Photos.exe|Microsoft|L'application Photos.
F|Video.UI.exe|Microsoft|Films et TV.
F|Music.UI.exe|Microsoft|Groove Musique.
F|Microsoft.Media.Player.exe|Microsoft|Le Lecteur multimédia.
F|wmplayer.exe|Microsoft|Lecteur Windows Media.
F|HxOutlook.exe|Microsoft|L'ancienne application Courrier.
F|HxTsr.exe|Microsoft|Synchronisation de Courrier et Calendrier.
F|olk.exe|Microsoft|Le nouvel Outlook.
F|Cortana.exe|Microsoft|L'assistant Cortana.
F|Copilot.exe|Microsoft|L'assistant Copilot.
F|XboxPcApp.exe|Microsoft|L'application Xbox.
F|OneDriveStandaloneUpdater.exe|Microsoft|Mise à jour de OneDrive.
F|ms-teams.exe|Microsoft|Microsoft Teams (réunions et discussions).
F|Teams.exe|Microsoft|Microsoft Teams (réunions et discussions).
F|Skype.exe|Microsoft|Skype (appels et messages).
f|OneDrive.exe|Microsoft|OneDrive : synchronise vos fichiers dans le cloud. Le fermer met la synchronisation en pause.
f|FileCoAuth.exe|Microsoft|OneDrive : permet de modifier un fichier Office à plusieurs.
f|Microsoft.SharePoint.exe|Microsoft|OneDrive : synchronise les dossiers SharePoint.
f|msedgewebview2.exe|Microsoft|Affiche des pages web à l'intérieur d'autres applications (Widgets, Teams...).
F|MicrosoftEdgeUpdate.exe|Microsoft|Mise à jour de Microsoft Edge.
F|identity_helper.exe|Microsoft|Aide de Microsoft Edge (connexion au compte).
F|msedge.exe|Microsoft|Le navigateur Microsoft Edge.
F|iexplore.exe|Microsoft|Internet Explorer (ancien navigateur).
F|WINWORD.EXE|Microsoft|Microsoft Word. Enregistrez votre document avant de fermer.
F|EXCEL.EXE|Microsoft|Microsoft Excel. Enregistrez votre classeur avant de fermer.
F|POWERPNT.EXE|Microsoft|Microsoft PowerPoint. Enregistrez avant de fermer.
F|ONENOTE.EXE|Microsoft|Microsoft OneNote.
F|OUTLOOK.EXE|Microsoft|Microsoft Outlook (courrier).
F|MSACCESS.EXE|Microsoft|Microsoft Access (bases de données).
f|OfficeClickToRun.exe|Microsoft|Mises à jour et fonctionnement de Microsoft Office.
F|OfficeC2RClient.exe|Microsoft|Mise à jour de Microsoft Office.
F|SDXHelper.exe|Microsoft|Aide de Microsoft Office (mises à jour de contenu).
F|msoia.exe|Microsoft|Télémétrie de Microsoft Office.
F|Code.exe|Microsoft|Visual Studio Code (éditeur de code). Enregistrez avant de fermer.
F|devenv.exe|Microsoft|Visual Studio (développement). Enregistrez avant de fermer.
f|PowerToys.exe|Microsoft|PowerToys : petits outils pour Windows.
F|SimpleTask.exe|SimpleTask|Ce gestionnaire de tâches simplifié.

# ---------- Pilotes : NVIDIA ----------
V|NVDisplay.Container.exe|NVIDIA|Pilote de la carte graphique NVIDIA.
V|nvcontainer.exe|NVIDIA|Services du pilote NVIDIA.
F|NVIDIA Share.exe|NVIDIA|Superposition NVIDIA (enregistrement, captures en jeu).
F|NVIDIA Web Helper.exe|NVIDIA|Aide internet de GeForce Experience.
F|NVIDIA Overlay.exe|NVIDIA|Superposition de l'application NVIDIA en jeu.
F|NVIDIA app.exe|NVIDIA|L'application NVIDIA (réglages, pilotes).
F|nvsphelper64.exe|NVIDIA|Aide de ShadowPlay (enregistrement en jeu).
F|NVIDIA GeForce Experience.exe|NVIDIA|GeForce Experience (pilotes, optimisation des jeux).
F|nvtelemetrycontainer.exe|NVIDIA|Télémétrie NVIDIA.
# ---------- Pilotes : AMD ----------
V|atiesrxx.exe|AMD|Service du pilote de carte graphique AMD.
V|atieclxx.exe|AMD|Pilote de carte graphique AMD (session utilisateur).
V|amdfendrsr.exe|AMD|Service de récupération du pilote graphique AMD.
F|RadeonSoftware.exe|AMD|Le logiciel AMD Radeon (réglages graphiques).
F|AMDRSServ.exe|AMD|Service du logiciel AMD Radeon (enregistrement, superposition).
F|AMDRSSrcExt.exe|AMD|Extension du logiciel AMD Radeon.
F|cncmd.exe|AMD|Lanceur du logiciel AMD Radeon.
# ---------- Pilotes : Intel ----------
V|igfxEM.exe|Intel|Pilote graphique Intel (gestion des écrans).
V|igfxCUIService.exe|Intel|Service du pilote graphique Intel.
V|IntelCpHDCPSvc.exe|Intel|Pilote graphique Intel : protection des vidéos (HDCP).
V|IntelCpHeciSvc.exe|Intel|Pilote Intel : communication avec la puce de gestion.
V|jhi_service.exe|Intel|Pilote Intel : technologie de sécurité de la carte mère.
V|LMS.exe|Intel|Pilote Intel : gestion à distance de la carte mère.
V|RstMwService.exe|Intel|Pilote Intel Rapid Storage (disques).
V|IAStorDataMgrSvc.exe|Intel|Pilote Intel Rapid Storage (disques).
V|esif_uf.exe|Intel|Pilote Intel de gestion de la chaleur et de l'énergie.
V|IntelAudioService.exe|Intel|Pilote audio Intel.
V|OneApp.IGCC.WinService.exe|Intel|Service du Centre de commande graphique Intel.
V|ibtsiva.exe|Intel|Pilote Bluetooth Intel.
V|WMIRegistrationService.exe|Intel|Pilote Intel (informations sur le matériel).
F|IGCC.exe|Intel|Centre de commande graphique Intel (réglages).
f|IAStorIcon.exe|Intel|Icône Intel Rapid Storage près de l'horloge.
F|IntelGraphicsSoftware.exe|Intel|Logiciel graphique Intel (réglages).
# ---------- Pilotes : son, touchpad, Bluetooth ----------
V|RtkAudUService64.exe|Realtek|Pilote audio Realtek. Le fermer peut couper le son.
V|RAVBg64.exe|Realtek|Pilote audio Realtek (arrière-plan).
V|RtkBtManServ.exe|Realtek|Pilote Bluetooth Realtek.
f|RtkNGUI64.exe|Realtek|Panneau de réglages audio Realtek.
f|RAVCpl64.exe|Realtek|Panneau de réglages audio Realtek.
V|NahimicSvc64.exe|A-Volute|Pilote audio Nahimic (effets sonores).
V|NahimicSvc32.exe|A-Volute|Pilote audio Nahimic (effets sonores).
V|WavesSvc64.exe|Waves Audio|Pilote audio Waves MaxxAudio.
V|WavesSysSvc64.exe|Waves Audio|Pilote audio Waves MaxxAudio.
V|DAX3API.exe|Dolby|Pilote audio Dolby.
V|SynTPEnh.exe|Synaptics|Pilote du pavé tactile Synaptics.
V|ETDCtrl.exe|ELAN|Pilote du pavé tactile ELAN.
# ---------- Navigateurs ----------
F|chrome.exe|Google|Le navigateur Google Chrome.
F|firefox.exe|Mozilla|Le navigateur Firefox.
F|opera.exe|Opera|Le navigateur Opera.
F|brave.exe|Brave Software|Le navigateur Brave.
F|vivaldi.exe|Vivaldi Technologies|Le navigateur Vivaldi.
F|GoogleCrashHandler.exe|Google|Envoie les rapports de plantage de Chrome.
F|GoogleCrashHandler64.exe|Google|Envoie les rapports de plantage de Chrome.
F|GoogleUpdate.exe|Google|Mise à jour de Google Chrome.
F|elevation_service.exe|Google|Service de mise à jour du navigateur (Chrome ou Edge).
F|crashpad_handler.exe|Divers|Envoie les rapports de plantage d'une application.
# ---------- Communication ----------
F|Discord.exe|Discord Inc.|Application de chat vocal et textuel.
F|Slack.exe|Slack Technologies|Slack (messagerie de travail).
F|Zoom.exe|Zoom|Zoom (réunions vidéo).
F|Telegram.exe|Telegram|Telegram (messagerie).
F|WhatsApp.exe|Meta|WhatsApp (messagerie).
F|WhatsApp.Root.exe|Meta|WhatsApp (messagerie).
F|Signal.exe|Signal|Signal (messagerie).
F|thunderbird.exe|Mozilla|Thunderbird (courrier).
F|TeamSpeak.exe|TeamSpeak|TeamSpeak (chat vocal).
F|ts3client_win64.exe|TeamSpeak|TeamSpeak 3 (chat vocal).
# ---------- Jeux ----------
F|steam.exe|Valve|Steam : bibliothèque de jeux.
F|steamwebhelper.exe|Valve|Steam : affiche les pages de la boutique et de la bibliothèque.
f|steamservice.exe|Valve|Service de Steam (installation, anti-triche de certains jeux).
F|gameoverlayui.exe|Valve|Superposition Steam en jeu.
F|EpicGamesLauncher.exe|Epic Games|Epic Games Launcher.
F|EpicWebHelper.exe|Epic Games|Epic Games : affiche les pages de la boutique.
F|Battle.net.exe|Blizzard|Battle.net (jeux Blizzard).
F|EADesktop.exe|Electronic Arts|L'application EA (jeux EA).
F|EABackgroundService.exe|Electronic Arts|Service de l'application EA.
F|Origin.exe|Electronic Arts|Origin (ancienne application de jeux EA).
F|UbisoftConnect.exe|Ubisoft|Ubisoft Connect (jeux Ubisoft).
F|upc.exe|Ubisoft|Ubisoft Connect (jeux Ubisoft).
F|GalaxyClient.exe|GOG|GOG Galaxy (bibliothèque de jeux).
F|RiotClientServices.exe|Riot Games|Lanceur Riot (League of Legends, Valorant).
F|RiotClientUx.exe|Riot Games|Fenêtre du lanceur Riot.
f|vgtray.exe|Riot Games|Icône de l'anti-triche Riot Vanguard.
f|vgc.exe|Riot Games|Anti-triche Riot Vanguard. Nécessaire pour jouer à Valorant.
F|Overwolf.exe|Overwolf|Overwolf (outils et superpositions pour les jeux).
F|Medal.exe|Medal|Medal (enregistrement de moments de jeu).
F|obs64.exe|OBS Project|OBS Studio (enregistrement et diffusion vidéo).
F|Playnite.DesktopApp.exe|Playnite|Playnite (bibliothèque de jeux).
F|XboxAppServices.exe|Microsoft|Services de l'application Xbox.
# ---------- Musique et vidéo ----------
F|Spotify.exe|Spotify|Spotify (musique).
F|vlc.exe|VideoLAN|Lecteur vidéo VLC.
F|iTunes.exe|Apple|iTunes (musique, iPhone).
f|AppleMobileDeviceService.exe|Apple|Service Apple qui reconnaît l'iPhone branché au PC.
F|mpc-hc64.exe|MPC-HC|Lecteur vidéo Media Player Classic.
F|PotPlayerMini64.exe|Kakao|Lecteur vidéo PotPlayer.
F|foobar2000.exe|foobar2000|Lecteur de musique foobar2000.
F|Audacity.exe|Audacity|Audacity (édition audio).
# ---------- Bureautique, création, développement ----------
F|notepad++.exe|Notepad++|Notepad++ (éditeur de texte).
F|Acrobat.exe|Adobe|Adobe Acrobat (fichiers PDF).
F|AcroRd32.exe|Adobe|Adobe Reader (fichiers PDF).
F|AcroCEF.exe|Adobe|Adobe Acrobat : affichage de certaines parties de la fenêtre.
F|AdobeARM.exe|Adobe|Mise à jour d'Adobe Reader.
f|armsvc.exe|Adobe|Service de mise à jour d'Adobe Acrobat.
F|AdobeCollabSync.exe|Adobe|Adobe Acrobat : synchronisation des documents partagés.
F|Creative Cloud.exe|Adobe|Adobe Creative Cloud.
F|CCXProcess.exe|Adobe|Adobe Creative Cloud (fonctions en arrière-plan).
F|CCLibrary.exe|Adobe|Adobe Creative Cloud (bibliothèques).
F|AdobeIPCBroker.exe|Adobe|Adobe Creative Cloud (communication entre applications).
F|Adobe Desktop Service.exe|Adobe|Adobe Creative Cloud (service).
f|AdobeUpdateService.exe|Adobe|Service de mise à jour Adobe.
F|Photoshop.exe|Adobe|Adobe Photoshop. Enregistrez avant de fermer.
F|idea64.exe|JetBrains|IntelliJ IDEA (développement).
F|pycharm64.exe|JetBrains|PyCharm (développement Python).
f|python.exe|Python|Un programme écrit en Python. Le fermer l'arrête.
f|pythonw.exe|Python|Un programme écrit en Python (sans fenêtre). Le fermer l'arrête.
f|node.exe|OpenJS|Un programme écrit en JavaScript (Node.js). Le fermer l'arrête.
f|java.exe|Oracle|Un programme Java. Le fermer l'arrête.
f|javaw.exe|Oracle|Un programme Java (sans fenêtre). Le fermer l'arrête.
F|jusched.exe|Oracle|Vérifie les mises à jour de Java.
F|jucheck.exe|Oracle|Vérifie les mises à jour de Java.
F|WinRAR.exe|win.rar GmbH|WinRAR (archives zip, rar).
F|7zFM.exe|Igor Pavlov|7-Zip (archives).
F|7zG.exe|Igor Pavlov|7-Zip (compression ou extraction en cours).
F|Everything.exe|voidtools|Everything (recherche de fichiers).
F|ShareX.exe|ShareX|ShareX (captures d'écran).
F|Greenshot.exe|Greenshot|Greenshot (captures d'écran).
F|Lightshot.exe|Skillbrains|Lightshot (captures d'écran).
f|AutoHotkey.exe|AutoHotkey|Script AutoHotkey (raccourcis clavier personnalisés).
f|AutoHotkey64.exe|AutoHotkey|Script AutoHotkey (raccourcis clavier personnalisés).
F|CCleaner64.exe|Piriform|CCleaner (nettoyage).
F|qbittorrent.exe|qBittorrent|qBittorrent (téléchargements torrent).
F|uTorrent.exe|BitTorrent|µTorrent (téléchargements torrent).
F|Docker Desktop.exe|Docker|Docker Desktop.
f|com.docker.backend.exe|Docker|Service de Docker Desktop.
f|VBoxSVC.exe|Oracle|VirtualBox (machines virtuelles).
F|VirtualBox.exe|Oracle|VirtualBox (machines virtuelles).
F|vmware.exe|VMware|VMware Workstation (machines virtuelles).
F|vmware-tray.exe|VMware|Icône VMware près de l'horloge.
# ---------- Cloud ----------
F|Dropbox.exe|Dropbox|Dropbox (synchronisation de fichiers).
F|GoogleDriveFS.exe|Google|Google Drive (synchronisation de fichiers).
F|MEGAsync.exe|MEGA|MEGA (synchronisation de fichiers).
F|iCloudDrive.exe|Apple|iCloud Drive (synchronisation de fichiers).
F|iCloudServices.exe|Apple|Services iCloud.
# ---------- Prise en main à distance ----------
f|AnyDesk.exe|AnyDesk|AnyDesk (prise en main à distance). Fermez-le si vous ne l'utilisez pas.
f|TeamViewer.exe|TeamViewer|TeamViewer (prise en main à distance).
f|TeamViewer_Service.exe|TeamViewer|Service TeamViewer (prise en main à distance).
F|parsecd.exe|Parsec|Parsec (jeu et bureau à distance).
# ---------- Antivirus (ne pas fermer) ----------
V|AvastSvc.exe|Avast|Antivirus Avast.
f|AvastUI.exe|Avast|Fenêtre de l'antivirus Avast. La protection continue sans elle.
V|AVGSvc.exe|AVG|Antivirus AVG.
f|AVGUI.exe|AVG|Fenêtre de l'antivirus AVG. La protection continue sans elle.
V|ekrn.exe|ESET|Antivirus ESET.
f|egui.exe|ESET|Fenêtre de l'antivirus ESET. La protection continue sans elle.
V|vsserv.exe|Bitdefender|Antivirus Bitdefender.
V|bdservicehost.exe|Bitdefender|Antivirus Bitdefender.
f|bdagent.exe|Bitdefender|Fenêtre de l'antivirus Bitdefender.
V|mcshield.exe|McAfee|Antivirus McAfee.
V|mfemms.exe|McAfee|Antivirus McAfee.
V|NortonSecurity.exe|Gen Digital|Antivirus Norton.
V|avp.exe|Kaspersky|Antivirus Kaspersky.
f|avpui.exe|Kaspersky|Fenêtre de l'antivirus Kaspersky.
V|MBAMService.exe|Malwarebytes|Protection Malwarebytes.
f|mbamtray.exe|Malwarebytes|Icône Malwarebytes près de l'horloge.
F|Malwarebytes.exe|Malwarebytes|Fenêtre de Malwarebytes.
# ---------- Périphériques et fabricants ----------
F|lghub.exe|Logitech|Logitech G HUB (souris, clavier, casque).
f|lghub_agent.exe|Logitech|Logitech G HUB : applique les réglages de vos périphériques.
F|lghub_updater.exe|Logitech|Mise à jour de Logitech G HUB.
f|logioptionsplus_agent.exe|Logitech|Logitech Options+ : applique les réglages de la souris et du clavier.
f|RazerCentralService.exe|Razer|Service Razer Synapse (périphériques Razer).
F|Razer Synapse 3.exe|Razer|Razer Synapse (réglages des périphériques Razer).
F|iCUE.exe|Corsair|Corsair iCUE (éclairage, périphériques).
F|SteelSeriesGG.exe|SteelSeries|SteelSeries GG (périphériques SteelSeries).
f|SupportAssistAgent.exe|Dell|Dell SupportAssist (diagnostic, mises à jour).
f|LenovoVantageService.exe|Lenovo|Lenovo Vantage (réglages et mises à jour Lenovo).
f|ArmouryCrate.Service.exe|ASUS|ASUS Armoury Crate (éclairage, ventilateurs).
f|ArmouryCrate.UserSessionHelper.exe|ASUS|ASUS Armoury Crate (aide).
f|asus_framework.exe|ASUS|Logiciels ASUS (Armoury Crate, MyASUS).
f|MSI.CentralServer.exe|MSI|Logiciels MSI (MSI Center).
"""

_CODES = {
    "V": ("vital", "eleve"),
    "f": ("peut_etre_ferme", "faible"),
    "F": ("peut_etre_ferme", "aucun"),
}


def load_seed():
    entries = []
    for line in _DATA.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        code, nom, editeur, description = (x.strip() for x in line.split("|", 3))
        categorie, risque = _CODES[code]
        entries.append({
            "nom": nom,
            "description": description,
            "categorie": categorie,
            "risque": risque,
            "editeur": editeur,
            "source": "base_initiale",
        })
    return entries
