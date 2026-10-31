# Outlook mail düzenleme programı

#teknoloji #c++

## Proje: Classic Outlook Yerel Mail Yöneticisi

Windows üzerinde çalışan, bilgisayarda kurulu Microsoft Classic Outlook ile yerel olarak haberleşen bağımsız bir masaüstü uygulaması geliştir.

Uygulamanın amacı; kullanıcının Outlook gelen kutusundaki binlerce e-postayı konu başlığındaki anahtar kelimelere göre analiz etmek, sınıflandırmak, önizlemek ve kullanıcının onayıyla ilgili Outlook klasörlerine taşımaktır.

Bu sürüm yalnızca aşağıda belirtilen özellikleri içeren güvenli bir **V1 sürümü** olacaktır.

## 1. Temel Teknoloji

- Windows masaüstü uygulaması olmalı
- C# / .NET 8 kullanılmalı
- Arayüz için tercihen WPF kullanılmalı
- Bilgisayarda kurulu Classic Microsoft Outlook ile çalışmalı
- Outlook erişimi için Microsoft Outlook Object Model / COM Interop kullanılmalı
- Microsoft Graph kullanılmamalı
- Web sunucusu veya backend gerektirmemeli
- Kullanıcının mail şifresini istememeli veya saklamamalı
- Outlook'ta zaten oturum açılmış hesabı kullanmalı
- Mail verilerini harici sunucuya göndermemeli
- Tüm ayarlar ve uygulama verileri bilgisayarda yerel olarak tutulmalı

Uygulama mümkün olduğunca taşınabilir, hızlı ve sade olmalı.

## 2. Ana Çalışma Prensibi

Uygulamanın temel akışı: **Outlook → Gelen Kutusu → Mail Başlıklarını Tara → Keyword Kurallarını Uygula → Sonuçları Önizle → Kullanıcı Onayı → Taşı**

En önemli güvenlik prensibi: kullanıcının açık onayı olmadan hiçbir mail taşınmamalı veya silinmemelidir. Tarama işlemi Outlook üzerinde değişiklik yapmamalıdır.

## 3. Outlook Hesabını Algılama

Program açıldığında bilgisayarda kurulu Classic Outlook'u algıla. Outlook profilindeki mail hesaplarını listele. Birden fazla hesap varsa kullanıcı hangi hesabı yöneteceğini seçebilsin.

Örnek:

```
Outlook Hesabı
○ şirketmaili@firma.com
○ kişiselmail@example.com
[Bu hesabı kullan]
```

Son seçilen hesap yerel ayarlarda hatırlanabilir.

## 4. Dashboard

Ana sayfa sade ve bilgi odaklı olsun.

![[ChatGPT Image 19 Ağu 2026 13_48_07 (5).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_07 (6).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_07 (7).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_06 (3).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_07 (4).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_06 (1).png]]

![[ChatGPT Image 19 Ağu 2026 13_48_06 (2).png]]

Gösterilecek ana kartlar: Gelen Kutusu (6.392), Taşınacak (1.126), Silme Adayları (2.843), Sınıflandırılmamış (2.423).

Alt bölümde: son tarama zamanı, aktif keyword grubu sayısı, aktif kural sayısı, son işlem bilgisi gösterilebilir.

Ana aksiyon: **[Gelen Kutusunu Tara]**

## 5. Sol Menü

Uygulamanın ana navigasyonu: Dashboard, Mail Tara, Kurallar, Keyword Grupları, Silme Adayları, İşlem Geçmişi, Ayarlar. Navigasyon mümkün olduğunca sade tutulmalı.

## 6. Keyword Grupları

Kullanıcı birden fazla keyword'ü mantıksal bir grup altında toplayabilmeli.

Örnek grup adı: **TAKİP ETTİĞİM UÇAKLAR** — Keyword'ler: TC-111, TC-222, TC-333, TC-444, TC-555, TC-666, TC-777, TC-888, TC-999, TC-AAA.

Arayüz:

```
Keyword Grubu
Grup Adı: [ TAKİP ETTİĞİM UÇAKLAR ]
Keywordler:
TC-111      [Sil]
TC-222      [Sil]
TC-333      [Sil]
[ + Keyword Ekle ]
[Kaydet]
```

Keyword ekleme alanında birden fazla satır yapıştırılabilsin; uygulama bunları ayrı keyword olarak algılamalı. Boş satırlar temizlenmeli. Aynı keyword iki kez eklenmemeli. Keyword eşleşmesi büyük/küçük harfe duyarsız olmalı (`tc-111`, `TC-111`, `Tc-111` aynı keyword kabul edilmeli).

## 7. Kural Oluşturma

Kullanıcı keyword grubunu Outlook klasörüyle eşleştirebilmeli.

Örnek:

```
KURAL ADI: Takip Ettiğim Uçaklar
KEYWORD GRUBU: TAKİP ETTİĞİM UÇAKLAR
ARAMA ALANI: Mail Konusu
HEDEF KLASÖR: TAKİP ETTİKLERİM
[Kaydet]
```

V1 sürümünde yalnızca **mail konusu içerisinde keyword geçiyor mu?** kontrolü yapılmalıdır. Bir keyword grubundaki keyword'lerden herhangi biri mail konusunda bulunuyorsa kural eşleşmiş kabul edilmeli. Örneğin konu "A/C TC-111 DAILY STATUS" ve keyword "TC-111" ise eşleşme oluşmalıdır.

## 8. Outlook Klasör Seçimi

Hedef klasör kullanıcı tarafından Outlook klasör ağacından seçilebilsin. Örneğin:

```
Inbox
├── TAKİP ETTİKLERİM
├── Operasyon
├── Arşiv
└── _SİLME_ADAYLARI
```

Kullanıcının olmayan bir klasör seçmeye çalışması engellenmeli. İstenirse uygulama üzerinden yeni Outlook klasörü oluşturulabilsin (`[+ Yeni Outlook Klasörü]`).

## 9. Silme Adayları Sistemi

V1 sürümünde uygulama hiçbir maili kalıcı olarak otomatik silmemelidir. Silinmesi düşünülen mailler için özel bir kural türü oluşturulabilsin:

```
Kural: Gereksiz Mailler
Keyword Grubu: SİLİNECEKLER
İşlem: Silme Adayı
```

Bu mailler Outlook içerisindeki `_SİLME_ADAYLARI` klasörüne taşınmalıdır. Klasör yoksa kullanıcıya oluşturma seçeneği sun.

Program içerisinde ayrıca **Silme Adayları** ekranı bulunmalı. Burada aday mailler checkbox, tarih, mail konusu, eşleşen keyword, mevcut klasör bilgileriyle gösterilmeli.

| Seç | Konu | Eşleşen Keyword |
|---|---|---|
| ☑ | Monthly Newsletter | Newsletter |
| ☑ | Automatic Notification | Notification |
| ☐ | System Information | System |

Program V1 sürümünde bu adayları otomatik olarak kalıcı silmemelidir.

## 10. Mail Tarama

Kullanıcı **[Gelen Kutusunu Tara]** butonuna bastığında uygulama Outlook Inbox içindeki mailleri analiz etsin.

Örnek sonuç: 6392 mail tarandı — Takip Ettiğim Uçaklar: 1.126 eşleşme, Silme Adayları: 2.843 eşleşme, Sınıflandırılmamış: 2.423 mail.

Tarama sırasında: mail taşınmamalı, mail silinmemeli, okunmuş/okunmamış durumu değiştirilmemeli, Outlook üzerinde herhangi bir değişiklik yapılmamalı. Tarama yalnızca analiz yapmalıdır.

## 11. Tarama İlerlemesi

Binlerce mail bulunabileceği için uygulama donmuş görünmemeli.

```
Mail kutusu taranıyor...
████████████████░░░░ 72%
4.602 / 6.392
İptal
```

Tarama işlemi mümkün olduğunca UI thread'ini kilitlemeden yapılmalı. Kullanıcı taramayı iptal edebilmeli.

## 12. Kural Testi

Her kural için **[Kuralı Test Et]** butonu bulunmalı. Test sonucunda "6392 mail tarandı, 183 eşleşme bulundu" gösterilmeli. Altında eşleşen mailler listelenmeli. Bu işlem kesinlikle mail taşımamalıdır.

## 13. Önizleme Ekranı

Tarama sonucunda hangi mail üzerinde hangi işlemin yapılacağı açıkça gösterilmeli.

| Seç | İşlem | Mail Konusu | Eşleşme | Hedef |
|---|---|---|---|---|
| ☑ | Taşı | TC-111 Daily Status | TC-111 | TAKİP ETTİKLERİM |
| ☑ | Taşı | TC-555 Cabin Defect | TC-555 | TAKİP ETTİKLERİM |
| ☑ | Silme Adayı | Monthly Newsletter | Newsletter | _SİLME_ADAYLARI |
| ☐ | — | Shift Information | — | — |

Kullanıcı tek tek seçim yapabilmeli, tümünü seçebilmeli, seçimleri kaldırabilmeli, belirli bir kuralın sonuçlarını filtreleyebilmeli, mail konusuna göre arama yapabilmeli.

## 14. Uygulama Öncesi Onay

Kullanıcı **[Seçilen İşlemleri Uygula]** butonuna bastığında ikinci bir onay ekranı çıkmalı:

```
İşlemler uygulanacak
1.126 mail taşınacak.
483 mail Silme Adayları klasörüne taşınacak.
Toplam: 1.609 mail
Devam etmek istiyor musunuz?
[İptal] [Uygula]
```

Kullanıcı **Uygula** demeden işlem başlamamalı.

## 15. İşlem Sonucu

İşlem tamamlandığında rapor göster: Başarılı 1.598, Başarısız 11; Takip Ettiklerim: 1.120 mail, _SİLME_ADAYLARI: 478 mail; 11 mail taşınamadı. [Başarısızları Göster] [İşlemleri Geri Al]

Bir mail taşınamazsa tüm süreç durmamalıdır. Hata loglanmalı ve diğer maillerle devam edilmelidir.

## 16. İşlem Geçmişi

Yapılan her taşıma işlemi yerel veritabanında tutulmalıdır. Her kayıt en az şunları içermelidir: işlem zamanı, mail kimliği, mail konusu, eski Outlook klasörü, yeni Outlook klasörü, uygulanan kural, eşleşen keyword, işlem sonucu.

Örnek: 19.08.2026 13:42 — Mail: TC-111 Daily Status — Eşleşme: TC-111 — Eski: Inbox — Yeni: TAKİP ETTİKLERİM — Kural: Takip Ettiğim Uçaklar — Durum: Başarılı.

Yerel veri için SQLite kullanılabilir. Mail içeriğinin tamamı veritabanında saklanmamalıdır.

## 17. Geri Alma

Bu özellik V1 için kritik önemdedir. Kullanıcı son uyguladığı taşıma işlemlerini geri alabilmelidir.

```
Son İşlem
1.609 mail
19.08.2026 13:42
[Geri Al]
```

Geri alma işleminde program işlem geçmişindeki eski klasör bilgisini kullanarak maili eski klasörüne taşımalıdır. Geri alma öncesinde kullanıcıdan onay alınmalıdır. Bir mail kullanıcı tarafından işlem sonrasında manuel olarak başka bir yere taşındıysa uygulama bunu güvenli şekilde ele almalıdır. Hata oluşursa loglanmalı, diğer geri alma işlemleri devam etmelidir.

## 18. Sınıflandırılmamış Mailler

Hiçbir kuralla eşleşmeyen mailler ayrıca gösterilmeli (örn. Sınıflandırılmamış: 2.423 mail). Bu mailler üzerinde otomatik işlem yapılmamalıdır. Kullanıcı bunları inceleyerek daha sonra yeni keyword grupları oluşturabilir.

## 19. Kural Önceliği

Kuralların sırası değiştirilebilmeli. Bir mail birden fazla kuralla eşleşiyorsa V1'de ilk eşleşen aktif kural kullanılmalıdır. Kullanıcı kuralları sürükle-bırak veya yukarı/aşağı butonlarıyla sıralayabilsin.

## 20. Kural Aktif / Pasif

Her kural geçici olarak devre dışı bırakılabilsin. Pasif kurallar taramada kullanılmamalıdır. Keyword grupları silinmeden devre dışı bırakılabilmelidir.

## 21. Ayarların Saklanması

Aşağıdaki bilgiler program kapatıldığında kaybolmamalıdır: Outlook hesabı seçimi, keyword grupları, keyword'ler, kurallar, kural sırası, aktif/pasif durumları, hedef klasör bilgileri, işlem geçmişi. Yerel SQLite veritabanı kullanılabilir.

## 22. Veri Güvenliği

Uygulama mail şifresi istememeli, Outlook credential'larını saklamamalı, mail verilerini internete göndermemeli, telemetry kullanmamalı, kullanıcının mail içeriğini herhangi bir dış servise göndermemeli, yerel çalışmalıdır. Mümkün olduğunca mail gövdesini okumaktan kaçın. V1 sınıflandırması yalnızca Subject/Konu üzerinden yapılmalıdır.

## 23. Performans

Inbox içerisinde 5.000, 10.000, 20.000+ mail bulunabileceğini varsay. Outlook COM erişiminde gereksiz property okumalarından kaçın; tarama sırasında yalnızca gerekli alanları al (mail kimliği, subject, gerekli klasör bilgisi). Mail body veya attachment verilerini yükleme. UI tarama sırasında responsive kalmalı.

## 24. Hata Yönetimi

Ele alınması gereken durumlar: Outlook kurulu değil, Classic Outlook çalışmıyor, Outlook profilinde hesap bulunamadı, Outlook COM erişimi başarısız, kullanıcı hedef klasörü sildi, mail işlem sırasında başka yere taşındı, mail Outlook tarafından bulunamadı, Outlook kapatıldı, COM bağlantısı koptu, SQLite veritabanı erişim hatası. Tek bir mailde hata olması tüm batch işlemini durdurmamalıdır.

## 25. UI / UX Tasarımı

Arayüz kurumsal, modern ve sade olmalı; çocuksu veya aşırı renkli görünmemeli. Windows 11 ile uyumlu bir masaüstü uygulaması hissi vermeli. Tercih edilen yapı: sol navigasyon, üst başlık, dashboard kartları, veri tabloları, arama, filtre, açık durum mesajları, progress bar, confirmation dialog. Liste ekranlarında mümkün olduğunca yoğun fakat okunabilir veri göster.

## 26. İlk Kurulum Deneyimi

Program ilk kez açıldığında kısa kurulum akışı: 1) Classic Outlook Algılandı, 2) Outlook hesabını seç, 3) İlk keyword grubunu oluştur, 4) Hedef Outlook klasörünü seç, 5) İlk kuralı test et, 6) Dashboard'a geç.

## 27. Örnek Başlangıç Verisi

Uygulamanın test edilmesi için örnek keyword grubu: TAKİP ETTİĞİM UÇAKLAR (TC-111, TC-222, TC-333, TC-444, TC-555, TC-666, TC-777, TC-888, TC-999, TC-AAA). Kural: Ad "Takip Ettiğim Uçaklar", Keyword Grubu "TAKİP ETTİĞİM UÇAKLAR", Alan "Subject", İşlem "Taşı", Hedef "TAKİP ETTİKLERİM". Gerçek kullanıcının Outlook'unda bu verileri otomatik oluşturma; yalnızca geliştirme/test verisi olarak kullan.

## 28. V1'de Yapılmayacaklar

Gönderene göre filtreleme, To alanına göre filtreleme, CC alanına göre filtreleme, tarihe göre filtreleme, negatif keyword, "içermiyorsa" koşulları, regex, gelişmiş koşul kombinasyonları, AND/OR rule builder, mail body içerisinde keyword arama, attachment analizi, otomatik olarak yeni gelen mailleri sürekli izleme, background Outlook monitoring, otomatik mail silme, 30 gün sonra otomatik silme, Microsoft Graph, Exchange API, Microsoft 365 API, cloud backend, web paneli, mobil uygulama, AI sınıflandırması, LLM entegrasyonu, spam tahmini, mail özetleme, otomatik Outlook Rule oluşturma.

Kod mimarisini ileride genişletilebilir tasarla ancak bu özelliklerin hiçbirini mevcut UI veya kod akışına ekleme.

## 29. Önerilen Proje Mimarisi

Kod tek dosyada yazılmamalı; mantıksal katmanlara ayır:

```
OutlookMailManager/
├── Models/ (MailItemModel, KeywordGroup, MailRule, ScanResult, OperationHistory)
├── Services/ (OutlookService, MailScannerService, RuleEngineService, MailMoveService, UndoService, DatabaseService)
├── ViewModels/
├── Views/ (DashboardView, ScanView, RulesView, KeywordGroupsView, DeleteCandidatesView, HistoryView, SettingsView)
├── Data/
└── App.xaml
```

MVVM prensiplerine uygun geliştir.

## 30. Önemli Tasarım Prensibi

Bu uygulamada hızdan önce **güvenlik ve kontrol** önemlidir. Temel felsefe: TARA → GÖSTER → KULLANICI KONTROL ETSİN → ONAY AL → UYGULA → KAYDET → GEREKİRSE GERİ AL.

Hiçbir koşul altında "keyword bulundu → anında maili taşı" şeklinde kontrolsüz bir çalışma modeli kullanma.

## 31. Geliştirme Sırası

- **Faz 1:** WPF proje yapısı, Outlook COM bağlantısı, hesapların listelenmesi, Inbox erişimi
- **Faz 2:** SQLite, keyword grupları, CRUD işlemleri
- **Faz 3:** Kurallar, Outlook klasör seçimi, kural sırası
- **Faz 4:** Mail tarama motoru, Rule Engine, eşleşme sayıları
- **Faz 5:** Kural testi, önizleme ekranı
- **Faz 6:** Mail taşıma, Silme Adayları klasörü
- **Faz 7:** İşlem geçmişi, Undo / geri alma
- **Faz 8:** Hata yönetimi, performans optimizasyonu, UI iyileştirmeleri

Her fazdan sonra uygulamanın derlenebilir ve çalışabilir durumda kalmasını sağla.

## 32. Çıktı Beklentisi

1. Önce klasör/mimari yapısını oluştur.
2. Gerekli NuGet paketlerini belirt.
3. `.csproj` dosyasını hazırla.
4. Outlook COM entegrasyonunu oluştur.
5. SQLite katmanını oluştur.
6. Modelleri oluştur.
7. Servisleri oluştur.
8. ViewModel'leri oluştur.
9. WPF ekranlarını oluştur.
10. Tüm bağlantıları gerçekleştir.
11. Build hatalarını kontrol et.
12. Kullanılmayan placeholder kod bırakma.
13. TODO ile kritik özellik atlama.
14. Uygulamayı derlenebilir durumda teslim et.

Kod verirken yalnızca örnek/snippet verme; çalışan proje yapısını üret. Her önemli geliştirme aşamasında mevcut çalışan özellikleri bozma.

## 33. V1 Tamamlanma Kriterleri

Proje ancak aşağıdaki senaryo eksiksiz çalışıyorsa V1 tamamlanmış kabul edilmelidir:

1. Program açılıyor.
2. Classic Outlook algılanıyor.
3. Kullanıcı Outlook hesabını seçiyor.
4. Kullanıcı keyword grubu oluşturuyor.
5. Keyword'leri ekliyor.
6. Kullanıcı bir Outlook klasörü seçiyor.
7. Kural oluşturuyor.
8. Kuralı test ediyor.
9. Eşleşen mail sayısını görüyor.
10. Inbox taraması başlatıyor.
11. Sonuçları önizleme ekranında görüyor.
12. İstemediği mailleri listeden çıkarabiliyor.
13. İşlemi onaylıyor.
14. Seçilen mailler doğru Outlook klasörlerine taşınıyor.
15. Silme adayları `_SİLME_ADAYLARI` klasörüne taşınıyor.
16. İşlem geçmişi kaydediliyor.
17. Kullanıcı son işlemi geri alabiliyor.
18. Mailler eski Outlook klasörlerine geri dönüyor.
19. Outlook'taki okunmuş/okunmamış durumları gereksiz yere değişmiyor.
20. Uygulama kapanıp tekrar açıldığında kurallar ve keyword grupları korunuyor.

Bu kriterler tamamlanmadan V2 özelliklerine geçme.

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[Masaüstü uygulaması yapmak]]
