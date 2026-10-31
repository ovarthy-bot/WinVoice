# Locpic

#teknoloji

## Genel Tanım

Uygulama, kullanıcının fotoğraf galerisini tarayarak konum verisi olan tüm fotoğrafları kategorize edecek. Lokasyon alanı kullanıcı tarafından artırılıp azaltılabilmeli.

## 1. Hedef Platform ve Teknoloji Yığını

- **Platform:** Native Android (Kotlin, Jetpack Compose ile modern UI)
- **minSdkVersion:** Android 13 (API 33) öneriliyor; gerekirse API 31'e kadar düşürülebilir
- **ML/AI çerçevesi:** (belirlenmedi)

## Yalnızca Tasarım Görselleri Üret

Konum verilerine göre fotoğraf arşivini düzenleyen premium bir mobil uygulama için yalnızca yüksek kaliteli UI/UX tasarım görselleri hazırla.

**Uygulamanın temel işlevi:**

- Kullanıcının fotoğraf galerisini taramak
- Konum verisi bulunan bütün fotoğrafları tespit etmek
- Fotoğrafları ülke, şehir, bölge ve yakın konumlara göre kategorize etmek
- Fotoğrafların aynı lokasyon altında gruplanacağı coğrafi alanı/yakınlık yarıçapını kullanıcının artırıp azaltabilmesini sağlamak
- Kullanıcının fotoğraflarını harita ve galeri görünümleri üzerinden keşfetmesini sağlamak

**Tasarım karakteri:**

- Premium, sade, sinematik ve modern
- Yetişkin kullanıcılara hitap eden rafine bir görünüm
- Kullanışlı, erişilebilir ve anlaşılır
- Fotoğrafları tasarımın merkezinde tutan güçlü görsel hiyerarşi
- Geniş boşluklar, dengeli tipografi ve kontrollü renk kullanımı
- Koyu veya nötr tonlar üzerinde fotoğrafları öne çıkaran bir estetik
- Gereksiz süslemelerden, yoğun gradyanlardan ve kalabalık arayüzlerden kaçın
- Çocuksu illüstrasyonlar, oyuncak görünümlü ikonlar, aşırı yuvarlak bileşenler ve oyunlaştırılmış bir dil kullanma

**Birbirine benzemeyen 3 ayrı tasarım yönü:**

1. **Sinematik Karanlık:** Fotoğrafların güçlü biçimde öne çıktığı, koyu ve atmosferik, film arşivi hissi taşıyan tasarım.
2. **Editoryal Minimal:** Premium seyahat dergisi veya fotoğraf kitabını andıran, tipografi ve boşluk odaklı açık renkli tasarım.
3. **Harita Odaklı Teknolojik:** Haritanın ana deneyim olduğu, modern ve hassas veri görselleştirmeleri kullanan sofistike tasarım.

**Her tasarım yönünde hazırlanacak ekranlar:**

- İlk açılış ve izin ekranı
- Galeri tarama/analiz ekranı
- Ana keşif ekranı
- Harita üzerinde fotoğraf kümeleri
- Ülke, şehir ve lokasyon kategorileri
- Seçilen lokasyonun fotoğraf galerisi
- Lokasyon gruplama alanını/yakınlık yarıçapını artırıp azaltma arayüzü
- Fotoğraf detay ekranı

Her alternatif kendi renk sistemi, tipografi yaklaşımı, navigasyon yapısı ve bileşen karakterine sahip olmalı; bilgi mimarileri ve görsel yaklaşımları belirgin biçimde farklı olmalı. Şimdilik kod, backend, API, veri tabanı veya çalışan uygulama üretme — yalnızca tasarım konseptleri ve yüksek çözünürlüklü ekran görselleri.

## 2. Önce Ürün ve Deneyim Planını Çıkar

Konum verilerine göre fotoğraf galerisini düzenleyen bir mobil uygulama planlanıyor:

- Kullanıcının cihazındaki fotoğraf galerisini tarayacak
- Konum verisi bulunan fotoğrafları tespit edecek
- Fotoğrafları ülke, şehir, bölge ve yakın lokasyonlara göre kategorize edecek
- Fotoğrafların aynı lokasyon altında gruplanacağı coğrafi alanı/yakınlık yarıçapını kullanıcının artırıp azaltmasına izin verecek
- Fotoğrafları harita ve galeri görünümleri üzerinden keşfetmeyi sağlayacak

Bu aşamada backend kurma, API bağlama, kod yazma veya geliştirmeye başlama; önce kapsamı ve kullanıcı deneyimini planla.

**Aşağıdaki başlıklarda kapsamlı fakat uygulanabilir bir çalışma hazırla:**

1. Ürün vizyonu ve temel değer önerisi
2. Birincil ve ikincil hedef kullanıcı grupları
3. Kullanıcıların ihtiyaçları, motivasyonları ve sorunları
4. Temel kullanım senaryoları
5. İlk kullanımdan fotoğraf keşfine kadar uçtan uca kullanıcı yolculuğu
6. Galeri ve konum izinlerinin hangi aşamada, nasıl açıklanarak isteneceği
7. Bilgi mimarisi ve navigasyon yapısı
8. Gerekli ekranların tam listesi
9. Her ekranın amacı, ana içeriği ve kullanıcı aksiyonları
10. Fotoğraf tarama, sınıflandırma ve lokasyon kümeleme mantığının kullanıcıya nasıl anlatılacağı
11. Lokasyon alanı/yakınlık yarıçapı kontrolünün en anlaşılır kullanım modeli
12. Boş, yükleniyor, izin reddedildi, konum verisi bulunamadı ve hata durumları
13. Gizlilik ve güven hissini güçlendirecek deneyim kararları
14. Birbirinden belirgin biçimde farklı 3 tasarım yönü
15. Faz 1 için MVP kapsamı
16. Sonraki fazlara bırakılması gereken özellikler

Lokasyon alanı kontrolünü yalnızca teknik bir ayar gibi ele alma: kullanıcı küçük bir yarıçap seçtiğinde fotoğrafların ayrı mekânlara, büyük bir yarıçap seçtiğinde semt/şehir/bölge ölçeğinde daha geniş gruplara dönüşmesini görsel ve anlaşılır biçimde açıklayan bir deneyim tasarla.

**Çıktının sonunda özetle:**

- Önerilen ana kullanıcı akışı
- Faz 1 ekran listesi
- Faz 1 kabul kriterleri
- Tasarım başlamadan önce verilmesi gereken kritik kararlar

Yeni özellikler uydurarak kapsamı büyütme. Varsayımları ayrıca belirt. Henüz geliştirme yapma; önce planı onaya sun.

## Faz 1

Onaylanan ürün planına ve seçilen tasarım yönüne göre Faz 1 üretilebilir.

Başlamadan önce mevcut çalışmayı incele:

- Yarım kalmış, tekrarlanan veya seçilen tasarım yönüyle çelişen bölümleri temizle
- Kullanılmayan bileşenleri, gereksiz örnek içerikleri ve görsel tutarsızlıkları kaldır
- Çalışan ve gerekli kısımları sebepsiz yere yeniden yazma
- Önce mevcut temeli düzenli, tutarlı ve sürdürülebilir hâle getir

Ardından yalnızca onaylanan Faz 1 kapsamını uygula; yeni özellik ekleme ve kapsamı genişletme.

**Faz 1 öncelikleri:**

- İlk açılış deneyimi
- Galeri ve konum verisi izin akışı
- Fotoğraf tarama/analiz durumu
- Konum verisi bulunan fotoğrafların kategorize edilmiş galeri görünümü
- Harita üzerinde fotoğraf kümeleri
- Ülke, şehir ve lokasyon detayları
- Kullanıcının lokasyon gruplama alanını/yakınlık yarıçapını artırıp azaltabilmesi
- Seçilen yarıçapa göre fotoğraf gruplarının anlaşılır biçimde güncellenmesi
- Temel boş, yükleniyor, izin reddedildi ve hata durumları

**Kurallar:**

- Daha önce onaylanmamış özellikler ekleme
- Tasarım sistemine ve seçilen görsel yöne sadık kal
- Arayüz premium, sade, sinematik ve kullanılabilir olsun
- Çocuksu ikonlar, aşırı animasyonlar ve gereksiz dekorasyon kullanma
- Kullanıcı fotoğraflarını arayüzün merkezinde tut
- Gizlilik konusunda açık ve güven verici mikro metinler kullan
- Gerektiğinde gerçek servisler yerine kontrollü örnek veri kullan; ancak bunu açıkça belirt
- Mevcut teknik yapıya uygun, tekrar kullanılabilir bileşenler oluştur
- Erişilebilirlik, okunabilirlik ve farklı ekran boyutlarını gözet
- Her ana akış için yükleniyor, boş ve hata durumlarını tamamla

**Çalışma sırası:**

1. Mevcut yapıyı denetle ve temizle
2. Faz 1 kapsamıyla eşleşen ekran ve bileşenleri belirle
3. Tasarım sistemini tutarlı hâle getir
4. Ana kullanıcı akışını uygula
5. Lokasyon yarıçapı etkileşimini uygula
6. Hata ve boş durumlarını tamamla
7. Sonucu test et ve görsel tutarlılık kontrolü yap

Tamamlandığında neleri temizlediğini, neleri ürettiğini, hangi bölümlerde örnek veri kullandığını, yaptığın testleri ve Faz 1 dışında bıraktığın noktaları kısa ve net biçimde raporla. Faz 1 tamamlanmadan Faz 2'ye geçme.

## Faz 2

- Kullanıcı gruplarının üstüne tıkladığında o gruba ait tüm resimleri soldan sağa kaydırarak gezebilmeli. Şu an sadece örnek bir görsel ekranda gösteriliyor.
- Uygulama başlangıcında kullanıcıya "Tüm galeriyi tara", "Klasör seç" seçenekleri sunulsun.
- "Yerel tarama tamamlandı; geliştirme API'sine bağlanılamadı" uyarısı ekranın üst bölümünde çıkıyor.
- Listelenen resimler isteğe bağlı toplu şekilde silinebilmeli.
- Galeri sekmesinde şu an tüm görseller sunuluyor; bunun yerine kategorili liste ekranı oluşturulmalı. Bu ekranda ülke-şehir veya yarıçap ayarı filtresi eklenmeli.
- Uygulamadan çıkıp tekrar girildiğinde başlangıç sayfası gösterilmesi gereksiz; bunu kaldır. Sadece uygulamaya ilk kez girildiğinde bu ekran gösterilmeli.

## Faz 3

Herhangi bir resme tıklandığında tam ekranda gösterilsin. Resme uzun basılırsa ilgili resim seçilsin.

## ChatGPT ile Geliştirme (Doğrudan Klasör Yükleme)

- CHECKPOINT.md
- analysis_options.yaml
- README.md
- .gitignore
- pubspec.yaml
- android
- lib
- test
- assets

## İlgili Bağlantılar

- [[40_Teknoloji|Teknoloji]]
- [[İş Kartları düzenleme uygulaması]]
- [[Evdeki fiziksel varlıkların yaşam döngüsü yönetimi]]
