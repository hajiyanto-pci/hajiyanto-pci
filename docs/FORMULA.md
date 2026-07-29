# Formula Multi-Faktor Potensi Naik

Screener mencari saham yang **berpeluang lanjut naik** dengan kombinasi faktor (bukan satu indikator saja).

## Checklist wajib (default)

1. **Volume spike** ≥ 1.5× rata-rata 20 hari  
2. **Break resistance** (close ≥ high 20 hari sebelumnya)  
3. **Di atas MA20**  
4. **Akumulasi OBV** (OBV naik + volume beli dominan)  
5. **Money-flow positif** (CMF > 0 & MFI ≥ 45) → *proksi bandarmology*

## Skor 0–100 (bobot)

| Faktor | Bobot | Arti |
|--------|------:|------|
| Volume | 20 | Ada tekanan transaksi / minat |
| Break resistance | 18 | Struktur harga tembus supply |
| Money-flow / CMF+MFI | 15 | Proksi aliran dana (bandar) |
| Akumulasi OBV | 12 | Akumulasi bertahap |
| Stochastic | 12 | Momentum oscillator belum jelek |
| MACD | 8 | Tren jangka menengah |
| RSI | 8 | Tidak overbought ekstrem |
| Di atas MA | 7 | Tren masih bullish |

Default alert jika **skor ≥ 62**.

## Stochastic

- Ideal: %K silang naik di atas %D, dan %K belum > 85  
- Zona sehat: 20–70  

## Bandarmology — catatan penting

**Bandarmology sejati** memakai ringkasan broker / foreign net buy (IDX).  
Data itu **tidak gratis & stabil** di Yahoo Finance.

Di tool ini dipakai **proksi**:
- **CMF (Chaikin Money Flow)** — uang masuk/keluar dari close vs high-low  
- **MFI (Money Flow Index)** — RSI berbobot volume  
- **OBV** — akumulasi volume arah harga  

Ini mendekati konsep “bandar akumulasi”, tapi **bukan** data broker asli.

## Saran Stop Loss / Take Profit

Untuk setiap kandidat (posisi long breakout):

- **Entry** ≈ harga close sinyal  
- **SL** = lebih rendah antara `entry - 1.5×ATR(14)` dan swing-low 5 hari  
- **TP1** = entry + **1.5R** (R = jarak entry→SL)  
- **TP2** = entry + **2.5R**

Ini saran teknikal, bukan jaminan. Sesuaikan dengan risk management pribadi (mis. risiko max 1–2% modal).

## Cara pakai

```bash
python run_screener.py --as-of kemarin
python run_screener.py --mode open      # simulasi 09:10
python run_screener.py --mode midday    # break sesi 1
python run_screener.py --mode eod
```

Ubah bobot/filter di `config.yaml` (`require_money_flow`, `sl_atr_mult`, `tp1_rr`, dll).
