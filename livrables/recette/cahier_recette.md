# Cahier de recette

Résultats du 05/11/2026, sur PostgreSQL 15.10, PostGIS 3.5.0, QGIS 3.34. Le cahier est produit par `scripts/10_cahier_recette.py` à partir des tests du dossier `tests/` : chaque ligne vient d'un test exécuté, sauf la dernière série, qui reste à dérouler.

**202 cas exécutés, 0 en échec.** Les signalements et les interventions testés forment un jeu d'essai, marqué `jeu_essai = true` en base : les sources ne publient aucun historique de maintenance.

| Série | Vérifications | Cas | Réussies | Échouées | Non exécutées |
|---|---:|---:|---:|---:|---:|
| Reprise : rien ne se perd entre la source et la base | 11 | 13 | 11 | 0 | 0 |
| Contrôles : les erreurs posées exprès sont retrouvées | 5 | 10 | 5 | 0 | 0 |
| Structure : la base refuse ce qui est incohérent | 8 | 24 | 8 | 0 | 0 |
| Comptes et droits : chacun reste dans son périmètre | 10 | 35 | 10 | 0 | 0 |
| Exploitation : signalements et interventions | 15 | 19 | 15 | 0 | 0 |
| Format d'échange : les fichiers livrés, relus sans la base | 11 | 37 | 11 | 0 | 0 |
| Flux : une nouvelle publication, sur une copie de la base | 9 | 9 | 9 | 0 | 0 |
| Projets QGIS : rouverts avec le compte de chaque profil | 11 | 28 | 11 | 0 | 0 |
| Fenêtre QGIS : le parcours réel de chaque profil | 3 | 12 | 3 | 0 | 0 |
| Terrain : du paquet QField jusqu'à la base | 12 | 15 | 12 | 0 | 0 |
| Vérifications par un utilisateur | 6 | 0 | 0 | 0 | 6 |

## T-REP : Reprise : rien ne se perd entre la source et la base

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-REP-01 | chaque ligne de la source est reprise, fusionnée ou écartée, écart nul | 3 | réussi | SDE18 : 63093 lignes = 63093 points + 0 fusionnées + 0 écartées, écart 0 ; NANTES : 97473 lignes = 97473 points + 0 fusionnées + 0 écartées, écart 0 ; LOIRE : 18147 lignes = 18104 points + 33 fusionnées + 10 écartées, écart 0 |
| T-REP-02 | les règles de reprise et de valeurs non prévues ne relèvent aucun écart | 1 | réussi | 0 écart sur REP_01 à REP_04 et COH_01 |
| T-REP-03 | toute ligne non reprise de la publication Loire porte un motif et son contenu | 1 | réussi | 43 lignes en rejet, 0 sans motif |
| T-REP-04 | pas de doublon d'identifiant par gestionnaire, y compris à l'export | 1 | réussi | 0 identifiant en double |
| T-REP-05 | les 4 identifiants de foyer portés par deux objets à Nantes sont gardés, suffixés | 1 | réussi | 4 points suffixés -D2 |
| T-REP-06 | géométries valides, en Lambert 93, sur le territoire métropolitain | 1 | réussi | 173290 supports, 0 invalides, 0 hors de la métropole |
| T-REP-07 | la date 01/01/1970 du syndicat n'est pas reprise, mais elle est signalée | 1 | réussi | 0 reprises, 117 signalées par TEM_01 |
| T-REP-08 | les saillies probablement en millimètres ne sont pas converties en silence | 1 | réussi | saillie maximale reprise 11.00 m, 877 valeurs signalées par VAL_05 |
| T-REP-09 | toute valeur cible des correspondances existe dans la liste du standard | 1 | réussi | 92 correspondances, 0 orphelines |
| T-REP-10 | l'hypothèse « un point par support » du syndicat reste visible sur chaque point | 1 | réussi | 63093 points sur 63093 portent l'hypothèse |
| T-REP-11 | le rapprochement des deux bases du Cher classe chaque objet | 1 | réussi | {'absent_ccf': 4, 'absent_syndicat': 11, 'apparie': 5347, 'recode_probable': 14} |

## T-CTR : Contrôles : les erreurs posées exprès sont retrouvées

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-CTR-01 | une erreur posée sur un objet précis est retrouvée par la règle, sur cet objet | 6 | réussi | POS_02 : POS_02 relève EPRZ001001 ; POS_03 : POS_03 relève EPBO001001 ; POS_04 : POS_04 relève EPRZ001001 ; COH_05 : COH_05 relève EPOR001 ; TEM_03 : TEM_03 relève EPSH002001 ; VAL_06 : VAL_06 relève EPRZ170049 |
| T-CTR-02 | un point retiré sans motif casse le bilan et le signale en bloquant | 1 | réussi | REP_01 mesure un écart de 1 |
| T-CTR-03 | une valeur source absente des correspondances ressort, au lieu d'être perdue | 1 | réussi | 1 écart COH_01 sur VALEUR_INCONNUE |
| T-CTR-04 | une décision déjà prise sur un écart survit à une nouvelle passe de contrôle | 1 | réussi | décision relue : faux_positif |
| T-CTR-05 | la publication titrée Loire, située en Haute-Savoie, est bloquée par POS_05 | 1 | réussi | LOIRE : 18104 supports, départements trouvés : 74 |

## T-STR : Structure : la base refuse ce qui est incohérent

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-STR-01 | une valeur hors liste ou hors bornes est refusée sur le point lumineux | 6 | réussi | type_source-XENON : ForeignKeyViolation ; usage-Z9 : ForeignKeyViolation ; structure-ABC : ForeignKeyViolation ; statut-en panne : ForeignKeyViolation ; temperature_couleur-500 : CheckViolation ; puissance_w--10 : CheckViolation |
| T-STR-02 | une valeur hors liste ou hors bornes est refusée sur le support | 4 | réussi | type_support-XYZ : ForeignKeyViolation ; hauteur_m-90 : CheckViolation ; etat-cass\xe9 : ForeignKeyViolation ; date_pose-1800-01-01 : CheckViolation |
| T-STR-03 | deux points d'un même gestionnaire ne partagent pas un identifiant | 1 | réussi | identifiant refusé |
| T-STR-04 | un point lumineux sans support, ou sans commune, est refusé | 1 | réussi | support et commune obligatoires |
| T-STR-05 | un support qui porte un point ne peut pas être supprimé | 1 | réussi | suppression refusée |
| T-STR-06 | le format d'heure de la section 3.5 du standard est contrôlé | 7 | réussi | 22:00HL-True : 22:00HL : True ; 06:30TU-True : 06:30TU : True ; +30MN-True : +30MN : True ; 24:00HL-False : 24:00HL : False ; 22h00-False : 22h00 : False ; 22:60HL-False : 22:60HL : False ; 2200-False : 2200 : False |
| T-STR-07 | les chaînes exportées n'ont que les caractères permis par la section 4.4 | 3 | réussi | \xc9clairage public-Eclairage_public : Éclairage public donne Eclairage_public ; a/b c-a_b_c : a/b c donne a_b_c ; LED-3000.k_v2-LED-3000.k_v2 : LED-3000.k_v2 donne LED-3000.k_v2 |
| T-STR-08 | les listes de valeurs ont le nombre de codes du standard, avec XX et AU là où il les prévoit | 1 | réussi | {'usage': 14, 'type_source': 12, 'structure_luminaire': 12, 'support_luminaire': 11, 'eclairage_adaptatif': 4, 'statut_installation': 6} |

## T-ROL : Comptes et droits : chacun reste dans son périmètre

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-ROL-01 | un compte ne lit que les communes de son périmètre | 12 | réussi | metier.point_lumineux-demo_commune-communes0 : 6539 lignes, communes ['44143'] ; metier.point_lumineux-demo_entreprise-communes1 : 10446 lignes, communes ['44020', '44143'] ; metier.point_lumineux-demo_entreprise_b-communes2 : 4687 lignes, communes ['44215'] ; metier.support-demo_commune-communes0 : 6332 lignes, communes ['44143'] ; metier.support-demo_entreprise-communes1 : 10156 lignes, communes ['44020', '44143'] ; metier.support-demo_entreprise_b-communes2 : 4598 lignes, communes ['44215'] ; metier.armoire-demo_commune-communes0 : 136 lignes, communes ['44143'] ; metier.armoire-demo_entreprise-communes1 : 241 lignes, communes ['44020', '44143'] ; metier.armoire-demo_entreprise_b-communes |
| T-ROL-02 | l'administrateur voit tout le territoire | 1 | réussi | 178670 points |
| T-ROL-03 | une entreprise ne voit que ses interventions, pas celles d'une autre | 1 | réussi | entreprise A : [(1,)], entreprise B : [(2,)] |
| T-ROL-04 | hors de sa fiche, un compte ne peut ni écrire ni supprimer | 15 | réussi | UPDATE metier.point_lumineux SET puissance_w = 1-demo_commune : refusé par la base ; UPDATE metier.point_lumineux SET puissance_w = 1-demo_entreprise : refusé par la base ; UPDATE metier.point_lumineux SET puissance_w = 1-demo_lecture : refusé par la base ; DELETE FROM metier.support-demo_commune : refusé par la base ; DELETE FROM metier.support-demo_entreprise : refusé par la base ; DELETE FROM metier.support-demo_lecture : refusé par la base ; INSERT INTO exploitation.intervention (point_id, nature, insee, geom) SELECT id, 'CONTROLE', insee, geom FROM metier.point_lumineux LIMIT 1-demo_commune : refusé par la base ; INSERT INTO exploitation.intervention (point_id, nature, insee, geom) SELE |
| T-ROL-05 | le compte de lecture lit le format EclExt, pas les tables de travail | 1 | réussi | 178670 points au format d'échange |
| T-ROL-06 | une collectivité signale dans sa commune, jamais ailleurs | 1 | réussi | accepté à 44143 par demo_commune |
| T-ROL-07 | une entreprise ne change ni la nature, ni le titulaire, ni l'objet de l'intervention | 1 | réussi | nature, titulaire et objet refusés ; compte rendu accepté |
| T-ROL-08 | une entreprise ne peut pas modifier l'intervention d'une autre | 1 | réussi | 0 ligne modifiée |
| T-ROL-09 | aucun compte de démonstration n'est superutilisateur ni propriétaire d'objet | 1 | réussi | 9 rôles vérifiés |
| T-ROL-10 | un profil ordinaire ne peut pas créer de compte | 1 | réussi | refusé par la base |

## T-EXP : Exploitation : signalements et interventions

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-EXP-01 | la commune et la position d'une fiche viennent de l'objet choisi | 1 | réussi | commune 44143, écart de position 0.0 m |
| T-EXP-02 | une fiche sans objet est refusée | 1 | réussi | refusée par la base |
| T-EXP-03 | on ne saute pas d'étape dans le suivi d'une intervention | 3 | réussi | A_PLANIFIER-REALISEE : A_PLANIFIER vers REALISEE refusé ; A_PLANIFIER-EN_COURS : A_PLANIFIER vers EN_COURS refusé ; PLANIFIEE-REALISEE : PLANIFIEE vers REALISEE refusé |
| T-EXP-04 | une intervention réalisée ou annulée ne repart pas en arrière | 1 | réussi | annulée définitivement |
| T-EXP-05 | une intervention planifiée doit avoir une date prévue | 1 | réussi | refusée sans date |
| T-EXP-06 | une intervention réalisée doit avoir une date et un compte rendu | 3 | réussi | None-Fait : refusée ; 2026-11-01-None : refusée ; 2026-11-01-    : refusée |
| T-EXP-07 | un changement de matériel doit préciser la nouvelle source et la nouvelle puissance | 1 | réussi | refusé sans nouveau matériel |
| T-EXP-08 | un changement de source met à jour le point, sa date valideDe, et le format EclExt | 1 | réussi | SHP 77.0 W devient LED 40.0 W, valideDe 20261015 |
| T-EXP-09 | un dépannage à l'identique ne change pas le matériel, ni sa date de validité | 1 | réussi | point inchangé |
| T-EXP-10 | une dépose passe le point au statut dismantled, avec sa date de fin de validité | 1 | réussi | dismantled, valideJusque 20261020 |
| T-EXP-11 | le signalement passe à pris en compte, puis à clos quand l'intervention est réalisée | 1 | réussi | OUVERT, PRIS_EN_COMPTE, puis CLOS |
| T-EXP-12 | l'entreprise peut clore elle-même un remplacement, le patrimoine suit malgré ses droits limités | 1 | réussi | type de source lu après clôture : LED |
| T-EXP-13 | chaque changement est journalisé avec son auteur, ses valeurs avant et après | 1 | réussi | SHP vers LED, par postgres |
| T-EXP-14 | une décision sur un écart de contrôle est signée par le compte qui la prend | 1 | réussi | signée par demo_admin |
| T-EXP-15 | toutes les fiches d'exploitation de la base sont marquées jeu d'essai | 1 | réussi | 14 fiches sur 14 |

## T-ECL : Format d'échange : les fichiers livrés, relus sans la base

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-ECL-01 | le dossier contient les données et une fiche de métadonnées nommée selon la section 5.2 | 3 | réussi | SDE18 : fr-241800549-eclairage-exterieur-Cher-20261105.xml ; NANTES : fr-244400404-eclairage-exterieur-Nantes-Metropole-20261105.xml ; LOIRE : fr-200065886-eclairage-exterieur-publication-Loire-20261105.xml |
| T-ECL-02 | le fichier a autant de points que la base, sans point retiré | 3 | réussi | SDE18 : 63093 points dans le fichier, 63093 dans la base ; NANTES : 97473 points dans le fichier, 97473 dans la base ; LOIRE : 18104 points dans le fichier, 18104 dans la base |
| T-ECL-03 | géométrie ponctuelle en Lambert 93, nom de couche et de colonnes du standard | 3 | réussi | SDE18 : Point, 2154, 27 attributs ; NANTES : Point, 2154, 27 attributs ; LOIRE : Point, 2154, 27 attributs |
| T-ECL-04 | identifiants uniques, avec les seuls caractères permis par la section 4.4 | 3 | réussi | SDE18 : 63093 identifiants distincts, 0 mal formés ; NANTES : 97473 identifiants distincts, 0 mal formés ; LOIRE : 18104 identifiants distincts, 0 mal formés |
| T-ECL-05 | les dates sont écrites sur 8 chiffres, AAAAMMJJ, et sont de vraies dates | 9 | réussi | valideDe-SDE18 : 15056 dates, 0 fautives ; valideDe-NANTES : 0 dates, 0 fautives ; valideDe-LOIRE : 0 dates, 0 fautives ; valideJusque-SDE18 : 0 dates, 0 fautives ; valideJusque-NANTES : 0 dates, 0 fautives ; valideJusque-LOIRE : 0 dates, 0 fautives ; datePremiereInstallation-SDE18 : 0 dates, 0 fautives ; datePremiereInstallation-NANTES : 0 dates, 0 fautives ; datePremiereInstallation-LOIRE : 3722 dates, 0 fautives |
| T-ECL-06 | toutes les valeurs énumérées appartiennent aux listes du standard | 3 | réussi | SDE18 : 5 listes vérifiées, 0 écart ; NANTES : 5 listes vérifiées, 0 écart ; LOIRE : 5 listes vérifiées, 0 écart |
| T-ECL-07 | un attribut que la source ne donne pas reste vide ou inconnu : l'export ne comble rien | 3 | réussi | SDE18 : attributs absents de la source : typeSource, usage, estAdaptatif, puissance, temperatureCouleur, extinctionNuit ; NANTES : attributs absents de la source : valideDe, usage, extinctionNuit, estAdaptatif ; LOIRE : attributs absents de la source : valideDe |
| T-ECL-08 | le CSV donne les mêmes objets que le GeoPackage, avec des booléens en true et false | 3 | réussi | SDE18 : 63093 lignes, valeurs de eclairagePublic : ['false', 'true'] ; NANTES : 97473 lignes, valeurs de eclairagePublic : ['false', 'true'] ; LOIRE : 18104 lignes, valeurs de eclairagePublic : ['true'] |
| T-ECL-09 | la fiche de métadonnées déclare le standard, et se dit non conforme tant qu'il manque un attribut | 3 | réussi | SDE18 : pass = false ; Attributs obligatoires absents de la source : estAdaptatif, extinctionNuit, puissance, temperatureCouleur, typeSource, usage. ; NANTES : pass = false ; Attributs obligatoires absents de la source : estAdaptatif, extinctionNuit, usage, valideDe. ; LOIRE : pass = false ; Attributs obligatoires absents de la source : valideDe. |
| T-ECL-10 | les listes du cahier recette-geo sont celles de la base, valeur pour valeur | 1 | réussi | 6 listes identiques, 11 attributs obligatoires |
| T-ECL-11 | le contrôle indépendant par recette-geo refuse les lots et retrouve l'anomalie de territoire | 3 | réussi | SDE18-1 : NON RECEVABLE : 1 anomalie bloquante (maximum 0) ; 4 763,0 anomalies majeures pour mille objets (maximum 20) ; NANTES-0 : NON RECEVABLE : 3 021,6 anomalies majeures pour mille objets (maximum 20) ; LOIRE-18104 : NON RECEVABLE : 18 104 anomalies bloquantes (maximum 0) ; 1 486,5 anomalies majeures pour mille objets (maximum 20) |

## T-FLX : Flux : une nouvelle publication, sur une copie de la base

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-FLX-01 | le nouveau lot devient le lot courant, l'ancien reste en base | 1 | réussi | 20261105 (97473 lignes), 20261201 (97470 lignes, courant) |
| T-FLX-02 | le différentiel entre les deux lots annonce exactement ce qui a changé | 1 | réussi | {'ajout': 2, 'modification': 4, 'retrait': 5}, champ modifié : ['puissance_du_foyer_w'] |
| T-FLX-03 | un point absent du nouveau lot est retiré et daté, jamais supprimé, et sort de l'export | 1 | réussi | 5 points gardés, retirés le ['2026-12-01'], 5 supports retirés |
| T-FLX-04 | une valeur changée dans la source est mise à jour | 1 | réussi | puissances relues : [77.0] |
| T-FLX-05 | un nouveau foyer de la source est créé, avec son support, et part à l'export | 1 | réussi | 2 points à l'export, 2 supports créés |
| T-FLX-06 | un point, un support et une armoire corrigés après la reprise ne sont pas écrasés par la nouvelle publication | 1 | réussi | point : 999.0 W alors que la source dit 77 W ; support : 12.5 m ; armoire déplacée de 10 m conservée |
| T-FLX-07 | relancer la reprise sans nouveau lot ne réécrit aucune ligne | 1 | réussi | numéros de transaction identiques sur les points, les supports et les armoires : True |
| T-FLX-08 | le bilan de reprise reste à zéro après le nouveau lot, et le contrôle ne signale aucune perte | 1 | réussi | 97470 lignes = 97470 points, écart 0, 0 écart REP_01 |
| T-FLX-09 | un fichier déjà chargé (même empreinte) n'est pas chargé une seconde fois | 1 | réussi | [21:44:02] nantes : lot 5 déjà chargé (même empreinte) |

## T-APP : Projets QGIS : rouverts avec le compte de chaque profil

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-APP-01 | le projet s'ouvre, toutes ses couches sont valides, aucun mot de passe n'y est écrit | 3 | réussi | administrateur : 5 relations, thèmes : Contrôle de la reprise, Pannes et interventions, Patrimoine ; collectivite : 5 relations, thèmes : Contrôle de la reprise, Pannes et interventions, Patrimoine ; entreprise : 5 relations, thèmes : Pannes et interventions, Patrimoine |
| T-APP-02 | dans QGIS, le profil ne voit que son périmètre | 2 | réussi | collectivite-communes0 : 6539 points vus, communes ['44143'] ; entreprise-communes1 : 10446 points vus, communes ['44020', '44143'] |
| T-APP-03 | QGIS propose exactement les écritures permises par la base | 7 | réussi | administrateur-Points lumineux-droits0 : Points lumineux : ['Ajouter', 'Modifier', 'Supprimer'] ; collectivite-Points lumineux-droits1 : Points lumineux : lecture seule ; collectivite-Signalements-droits2 : Signalements : ['Ajouter'] ; collectivite-Interventions-droits3 : Interventions : lecture seule ; entreprise-Points lumineux-droits4 : Points lumineux : lecture seule ; entreprise-Signalements-droits5 : Signalements : lecture seule ; entreprise-Interventions-droits6 : Interventions : ['Modifier'] |
| T-APP-04 | les fiches sont organisées en onglets, avec les fiches liées | 3 | réussi | Points lumineux : Identification, Matériel, Photométrie, Allumage, Signalements, Interventions, Validité et origine ; Interventions : Intervention, Réalisation, Suivi ; Signalements : Signalement, Suivi, Terrain |
| T-APP-05 | les recherches enregistrées s'exécutent toutes sur la base, sans erreur | 3 | réussi | administrateur : 23 recherches, 0 en erreur ; collectivite : 23 recherches, 0 en erreur ; entreprise : 20 recherches, 0 en erreur |
| T-APP-06 | les listes de valeurs n'encombrent pas la barre de recherche | 1 | réussi | 18 couches exclues de la recherche |
| T-APP-07 | le formulaire d'intervention refuse les saisies incohérentes avant l'envoi à la base | 3 | réussi | realisee_sans_date_ni_compte_rendu-attendu0 : champs signalés : ['compte_rendu', 'date_realisee'] ; date_dans_le_futur-attendu1 : champs signalés : ['date_realisee'] ; changement_sans_nouveau_materiel-attendu2 : champs signalés : ['nouveau_type_source', 'nouvelle_puissance_w'] |
| T-APP-08 | à travers QGIS, la collectivité signale chez elle, jamais ailleurs, et la base signe la fiche | 1 | réussi | chez elle : True, ailleurs : False, déclarant demo_commune, statut OUVERT |
| T-APP-09 | à travers QGIS, l'entreprise ne peut ni changer la nature ni sauter d'étape | 1 | réussi | changer la nature : False, sauter des états : False |
| T-APP-10 | le modèle graphique de QGIS et la reprise SQL donnent le même résultat, objet par objet | 1 | réussi | 97465 objets comparés, valeurs renseignées {'typeSource': 97378, 'support': 86671, 'puissance': 97316, 'temperatureCouleur': 96276}, différences {'typeSource': 0, 'support': 0, 'puissance': 0, 'temperatureCouleur': 0}, écart de position maximal 0.0 m |
| T-APP-11 | la fiche d'un signalement retrouve le dossier des photos de terrain, depuis projets/ comme depuis projets/mon_postgres/ | 3 | réussi | administrateur : widget ExternalResource, dossier data/terrain/photos ; collectivite : widget ExternalResource, dossier data/terrain/photos ; entreprise : widget ExternalResource, dossier data/terrain/photos |

## T-IHM : Fenêtre QGIS : le parcours réel de chaque profil

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-IHM-01 | chaque profil ouvre son projet dans une vraie fenêtre QGIS et son parcours aboutit | 3 | réussi | administrateur : theme : ok, fenetre : ok, fiche_support : ok, fiche_ecart : ok ; collectivite : theme : ok, fenetre : ok, fiche_point : ok, signaler : ok ; entreprise : theme : ok, fenetre : ok, fiche_intervention : ok |
| T-IHM-02 | l'action « Signaler une panne » ouvre la fiche, le bouton OK enregistre, la base complète la fiche | 1 | réussi | fiche ouverte : True, OK actif : True, en base : ['demo_commune', 'OUVERT', '44143', 63357] |
| T-IHM-03 | les captures des supports de formation sont produites | 8 | réussi | fiche_point_materiel : 18 Ko ; fiche_support : 15 Ko ; fiche_signalement_saisie : 11 Ko ; fiche_intervention_realisation : 12 Ko ; fiche_ecart : 12 Ko ; qgis_administrateur_controle : 872 Ko ; qgis_collectivite_patrimoine : 632 Ko ; qgis_entreprise_interventions : 629 Ko |

## T-TER : Terrain : du paquet QField jusqu'à la base

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-TER-01 | le paquet s'ouvre hors de son dossier d'origine, sans connexion à la base ni mot de passe | 1 | réussi | couches : Communes, Plan IGN, Points lumineux, Signalements en cours, Signaler une panne ; fichiers : DCIM/, eclairage_terrain.qgs, reference.gpkg, signalements_terrain.gpkg |
| T-TER-02 | le paquet ne contient que le périmètre du compte, extrait avec ce compte | 1 | réussi | 6539 points sur 178670, communes ['44143'] |
| T-TER-03 | sur le téléphone, seule la couche de saisie est modifiable, et elle part vide | 1 | réussi | modifiable : ['Signaler une panne'], lignes au départ : 0 |
| T-TER-04 | le repère posé à 3 m d'un point ouvre une fiche remplie sur ce point | 1 | réussi | EPRZ003013, Impasse de la Morinière (Rezé), 3 m, fiche ouverte en 0.3 s |
| T-TER-05 | la fiche refuse un repère loin de tout point, et « Autre » sans description | 1 | réussi | loin de tout point : ['code_point'] ; Autre sans description : ['description'] |
| T-TER-06 | la photo passe par le widget de pièce jointe, avec un chemin relatif au projet, et le repère s'accroche aux points | 1 | réussi | widget ExternalResource, stockage relatif 1, accroche True |
| T-TER-07 | une ligne importée est signée par la base, placée sur son point, et une seconde passe ne crée pas de doublon | 1 | réussi | importee puis deja_importee, signé demo_commune, statut OUVERT, commune 44143 |
| T-TER-08 | chaque ligne fautive est refusée avec son motif, sans bloquer les autres | 1 | réussi | hors périmètre : Point hors du périmètre de ce compte ; point inconnu : Objet introuvable : renseigner un point lumineux, un support ou une armoire ; sans point : Aucun point lumineux rattaché ; nature inconnue : Nature de signalement inconnue ; sans identifiant : Identifiant de terrain absent ; identifiant faux : invalid input syntax for type uuid: "pas-un-identifiant" ; date future : new row for relation "signalement" violates check constraint "signalement_check1" ; photo avec dossier : new row for relation "signalement" violates check constraint "signalement_photo_check" |
| T-TER-09 | seuls la collectivité et l'administrateur peuvent verser des pannes | 4 | réussi | demo_commune-True : droit d'exécution : True ; demo_admin-True : droit d'exécution : True ; demo_entreprise-False : droit d'exécution : False ; demo_lecture-False : droit d'exécution : False |
| T-TER-10 | le dossier du téléphone arrive dans la base : bilan juste, photo copiée, refus expliqué, second import sans doublon | 1 | réussi | Reçues 3 : importées 2, déjà importées 0, refusées 1. |
| T-TER-11 | une panne encore dans le fichier -wal de SQLite, projet resté ouvert dans QField, n'est pas perdue | 1 | réussi | Reçues 1 : importées 1, déjà importées 0, refusées 0. |
| T-TER-12 | un chemin de photo venu du téléphone ne peut pas faire lire un fichier hors de l'envoi | 1 | réussi | chemin relatif, chemin absolu, remontée et extension interdite testés |

## T-MAN : Vérifications par un utilisateur

| N° | Vérification | Cas | Résultat | Constat |
|---|---|---:|---|---|
| T-MAN-01 | Une personne de la collectivité, avec le seul guide, signale une panne depuis la carte |  | non exécuté |  |
| T-MAN-02 | Une personne de l'entreprise, avec le seul guide, planifie puis clôt une intervention |  | non exécuté |  |
| T-MAN-03 | Un échantillon de points est comparé au terrain : position, type de source, puissance |  | non exécuté |  |
| T-MAN-04 | Un gestionnaire confirme ou écarte les correspondances marquées « arbitrage » |  | non exécuté |  |
| T-MAN-05 | Une session de formation est déroulée avec le plan proposé, et chronométrée |  | non exécuté |  |
| T-MAN-06 | Sur un vrai téléphone, avec QField, une personne de la collectivité déclare une panne avec photo, renvoie le projet, et la panne arrive dans la base |  | non exécuté |  |
