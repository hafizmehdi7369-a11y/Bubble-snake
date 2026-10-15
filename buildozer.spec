[app]
title = Bubble Snake
package.name = bubblesnake
package.domain = org.example
source.dir = .
source.include_exts = py
version = 1.0

# kivy is listed only so the SDL2 bootstrap pulls in the SDL libraries pygame needs
requirements = python3,kivy,pygame

orientation = portrait
fullscreen = 1

# Buildozer 1.6 docs ask for these two values (NDK 28c is also OK)
android.api = 36
android.ndk = 29
android.archs = arm64-v8a, armeabi-v7a
android.allow_backup = False
android.accept_sdk_license = True

[buildozer]
log_level = 2
warn_on_root = 1
