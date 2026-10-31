# Başlangıç

Bu kasa, notları bulmak için kuruludur; mükemmel sınıflandırmak için değil.

## Her yeni bilgi için tek karar

1. Hızlıca yaz: [[00 - Gelen Kutusu/Gelen Kutusu|Gelen Kutusu]]
2. Uygun olduğunda taşı: [[10 - İş/İş|İş]], [[20 - Kişisel/Kişisel|Kişisel]] veya [[30 - Projeler/Projeler|Projeler]]
3. Eski veya artık gerekmeyen notları taşı: [[90 - Arşiv/Arşiv|Arşiv]]

> [!tip] Kural
> Bir notun nereye gideceğinden emin değilsen **Gelen Kutusu**na koy. Notu taşımak için acele etme; doğru etiketleri vermen yeterli.

## Hızlı erişim

- [[00 - Gelen Kutusu/Gelen Kutusu|📥 Gelen Kutusu]]
- [[10 - İş/İş|✈️ İş ve havacılık]]
- [[20 - Kişisel/Kişisel|👤 Kişisel]]
- [[30 - Projeler/Projeler|🛠️ Projeler]]
- [[90 - Arşiv/Arşiv|🗄️ Arşiv]]
- [[99 - Sistem/Etiket Rehberi|🏷️ Etiket rehberi]]
- [[99 - Sistem/Kullanım Rehberi|Nasıl kullanılır?]]

## Son eklenen notlar

```dataview
LIST FROM !"90 - Arşiv"
WHERE file.name != "Başlangıç"
SORT file.ctime DESC
LIMIT 12
```
