[app]
title = ResearchRadar
package.name = researchradar
package.domain = com.yourname.researchradar
source.dir = .
source.include_exts = py,png,jpg,kv,atlas,json,db
version = 1.0.0
requirements = python3,kivy==2.3.0,requests,apscheduler,sqlalchemy,scikit-learn,nltk,scipy,plyer,kivymd
android.permissions = INTERNET,RECEIVE_BOOT_COMPLETED,SCHEDULE_EXACT_ALARM,POST_NOTIFICATIONS,FOREGROUND_SERVICE
android.api = 34
android.minapi = 26
android.ndk = 25c
android.arch = arm64-v8a
p4a.branch = develop
