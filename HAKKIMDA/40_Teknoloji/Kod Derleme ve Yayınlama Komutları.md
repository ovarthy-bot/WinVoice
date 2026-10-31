# Kod Derleme ve Yayınlama Komutları

#teknoloji #flutter #android

## Android App Bundle (.aab) üretme

```bash
flutter clean
flutter pub get
flutter build appbundle
```

## APK üretme (.apk)

```bash
flutter build apk
```

## Play Console'a yüklemeden sertifikayı doğrulama

```bash
keytool -printcert -jarfile build/app/outputs/bundle/release/app-release.aab
```

## Play Console Sürüm Hatası

**Hata Mesajı:** Sürüm kodu daha önce kullanıldı. Başka bir sürüm kodunu deneyin.

Bu, Google Play Console'un açık ara en sinir bozucu ve geliştiricileri en çok çileden çıkaran huylarından biridir. Bir "Sürüm Taslağını" (Release Draft) silsen bile, o sürüme eklediğin `.aab` dosyası silinmez; Google Play böyle çalışmıyor.

### Neden Taslağı Silmek İşe Yaramadı?

O dosya arka planda **App Bundle Gezgini (App Bundle Explorer)** adlı devasa bir depoya atılır. Play Console'un kuralı çok katıdır: bir `.aab` dosyası Google sunucularına bir saniyeliğine bile yüklenip işlendiyse, o "sürüm kodu" (version code) sonsuza dek yanmış demektir. Dosyayı silsen de, yayından kaldırsan da, iptal etsen de o sayıyı bir daha asla kullanamazsın.

### Kesin Çözüm: Güvenli Bir Atlayış Yap

Sürüm kodlarının ardışık (25, 26, 27) gitmesi zorunlu değildir; sadece bir öncekinden büyük olması yeterlidir. Birkaç tık ileri atlamak (örn. 30'a) tekrar aynı hatayı almayı önler.

**1. `pubspec.yaml` dosyasını güncelle:**

```yaml
version: 1.0.0+30
```

**2. `build.gradle.kts` dosyanı güncelle:**

```kotlin
val flutterVersionCode = project.findProperty("flutter.versionCode")?.toString() ?: "30"
```

**3. Terminali aç ve son kez temizleyip derle:**

```bash
flutter clean
flutter pub get
flutter build appbundle --target-platform android-arm,android-arm64,android-x64 --release
```

Yeni oluşan `.aab` dosyasını (içinde `30` sürüm kodunu barındıran) yüklediğinde Play Store bunu taze ve yeni bir sürüm olarak görecek ve hiçbir itiraz etmeden kabul edecektir.

**Ekstra bilgi:** Hangi sürüm kodlarının yandığını görmek istersen, Play Console'da sol menüden Sürüm (Release) → App Bundle Gezgini (App Bundle Explorer) sekmesine giderek Google'ın hafızasında tuttuğu tüm eski denemelerini ve sürüm kodlarını görebilirsin.

## Android Emulator çalıştırma

```bash
flutter clean
flutter pub get
flutter run -d emulator-5554
```

## Windows Emulator çalıştırma

```bash
flutter clean
flutter pub get
flutter run -d windows
```

Telefonu PC'ye kabloyla bağladıktan sonra USB'yi kontrol eden bağlı cihaz olarak değiştir, sonra bu cihaz yap ve dosya aktarımı seçeneğine tıkla.

## Chrome Emulator çalıştırma

```bash
flutter clean
flutter pub get
flutter run -d chrome
```

## Telefona uygulama yükleme

```bash
flutter build apk --release
flutter install -d R5CX10WKH5J
```

## Telefona uygulama yükleme (id ile)

```bash
flutter build apk --release
flutter install -d "adb-R5CX10WKH5J-hH3ZMk._adb-tls-connect._tcp"
```

## Kablosuz geliştirici modu

```bash
cd C:\Users\Onur\Documents\platform-tools
adb pair 192.168.68.109:
```

## Kotlin APK üretme ve kablosuz olarak telefona yükleme

```bash
./gradlew assembleDebug
./gradlew installUniversalDebug
```

Alternatif yöntem:

```bash
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r app\build\outputs\apk\arm64\debug\app-arm64-debug.apk
```

Başka bir örnek:

```bash
& "$env:LOCALAPPDATA\Android\Sdk\platform-tools\adb.exe" install -r app\build\outputs\apk\debug\FairScan-2.2.0-arm64-v8a.apk
```

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[Sıfırdan mobil uygulama üretim taslağı]]
- [[İş Kartları düzenleme uygulaması]]
