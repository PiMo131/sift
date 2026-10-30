# Benchmark 29 oktober 2026

> **Beperkte proef.** Eén opname, één fragment van vijf minuten, geen handmatig gecontroleerd referentietranscript.
> De cijfers hieronder zijn gemiddelde modelscores, aantallen woorden onder een drempel en onderlinge verschillen
> tussen modelruns; het zijn géén gemeten woordfoutpercentages en zeggen niets over de werkelijke transcriptiekwaliteit.
> Voor zo'n uitspraak is een onafhankelijk nagekeken referentietranscript nodig.

Fragment: 05:00 – 10:00 uit het interview (WhatsApp-export, AAC mono 48 kHz, 52:38 totaal).
Hardware: RTX 2000 Ada 8 GB (float16), i7-13700H (int8), 32 GB RAM. faster-whisper 1.2.1, beam 5, Silero VAD, woordtijdstempels.
Er is geen handmatig referentietranscript, dus "kwaliteit" is hier: gemiddelde woordzekerheid, aantal onzekere woorden, en steekproefsgewijs meelezen.

## Audiovarianten

| variant | bewerking | luidheid |
|---|---|---|
| raw | alleen 16 kHz mono | −32,6 LUFS |
| norm | highpass 80 Hz, compressor 3:1 (−30 dB, +4 dB makeup), loudnorm −16 LUFS (2-pass) | −16,2 LUFS |
| afftdn | als norm, plus ffmpeg-ruisfilter afftdn vóór de compressor | −16 LUFS |
| nr | norm, daarna noisereduce (niet-stationair, 60%) | −16 LUFS |

## Resultaten

| run | device | tijd (s) | × realtime | woorden | gem. zekerheid | < 0,6 | < 0,4 |
|---|---|---|---|---|---|---|---|
| large-v3, raw | GPU* | 619 | 0,5* | 876 | 0,870 | 105 | 44 |
| large-v3, norm | GPU | 41 | 7,3 | 898 | 0,905 | 78 | 42 |
| large-v3, afftdn | GPU | 32 | 9,4 | 883 | 0,897 | 89 | 29 |
| large-v3, nr | GPU | 30 | 10,1 | 904 | 0,892 | 89 | 46 |
| large-v3, norm | CPU int8 | 201 | 1,5 | 911 | 0,911 | 66 | 28 |
| turbo, norm | GPU | 12 | 25,7 | 864 | 0,890 | 81 | 32 |
| turbo, norm | CPU int8 | 119 | 2,5 | 874 | 0,893 | 80 | 37 |
| Qwen3-ASR 1.7B, norm | GPU | 61 | 5,0 | 386 | n.v.t. | n.v.t. | n.v.t. |
| CrisperWhisper (CT2), norm | GPU | 897* | 0,3* | 353 | 0,458 | 238 | 144 |

\* gemeten terwijl meerdere modellen de GPU deelden; niet representatief.

Onderlinge afwijking (woordfoutpercentage tussen runs): large-v3 norm vs raw 12%, large-v3 vs turbo 15%, turbo GPU vs turbo CPU 7%, large-v3 GPU vs CPU 9%.

## Conclusies

1. **Normaliseren helpt duidelijk.** Zelfde model, zelfde clip: 105 → 78 onzekere woorden, aandeel woorden ≥ 0,8 van 77% naar 83%. Bij meelezen ook inhoudelijk beter: zachte woorden aan het einde van zinnen worden vaker goed gehoord.
2. **Ruisonderdrukking voegt niets toe** bij deze opname. afftdn en noisereduce scoren gelijk of iets lager dan alleen normaliseren. Standaard uit, als optie beschikbaar voor rumoerige opnames.
3. **large-v3 is het beste model**, turbo een goede snelle tweede. Turbo maakt merkbaar meer fouten in de zachte passages (verkeerde, maar klankgelijke woorden).
4. **CPU is bruikbaar.** Turbo op CPU: 2,5× realtime, zelfde kwaliteit als GPU. large-v3 op CPU: 1,5× realtime, een uur audio in ca. 40 minuten. int8 op CPU gaf zelfs iets hogere zekerheden dan float16 op GPU; verschil is klein en kan ruis zijn.
5. **Modellen nooit tegelijk op één GPU draaien.** Twee of meer modellen in 8 GB VRAM dwingen swappen naar gedeeld geheugen: turbo ging van 12 s naar 453 s. De tool draait modellen na elkaar en cachet de uitkomst.
6. **Qwen3-ASR valt af als basismodel** voor deze spreker: laat meer dan de helft van de woorden weg, verhaspelt de rest, geen woordzekerheid, tijdstempels alleen met een extra alignermodel. Het blijft als optionele extra stem beschikbaar in Sift.
7. **CrisperWhisper valt af** in de faster-whisper-conversie: aangepaste tokenizer levert aaneengeplakte woorden, herhaallussen en honderden filler-tags. Eventueel later via de originele transformers-pipeline testen.
8. **Meerdere modellen combineren** blijft zinvol, maar dan large-v3 + turbo (en eventueel large-v3 CPU-int8 als derde stem): ze verschillen 15% van de woorden, precies de passages die handmatig nagekeken moeten worden.

## Bestanden

- `bench_whisper.py <audio.wav> <model> <label> [cuda|cpu]`: één run, schrijft `<label>.json` (woorden met tijd en zekerheid) en `<label>.txt`.
- `bench_qwen.py <audio.wav> <label>`: Qwen3-ASR-run.
- `compare.py [labels…]`: statistieken, onderlinge woordfoutpercentages en zekerheidsverdeling.
- Audio en transcripten van het interview zelf staan niet in de repository (privacy).
