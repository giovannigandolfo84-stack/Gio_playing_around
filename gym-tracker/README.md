# Gym Tracker (Expo · iPhone)

App per tracciare gli allenamenti in palestra.

- **Allena**: suggerisce la prossima scheda (rotazione), avvia la sessione.
- **Sessione**: kg × rip per serie, valori della volta precedente, spunta serie → timer di recupero con vibrazione (±15s / salta), aggiungi/rimuovi serie ed esercizi.
- **Programma**: schede modificabili (serie, rip, recupero, ordine). Backup/ripristino JSON.
- **Storico**: sessioni con durata, volume, dettaglio serie.
- **Progressi**: 1RM stimato (Epley), carico max, volume per sessione.

Dati salvati in locale sul telefono (AsyncStorage).

## Avvio su iPhone

1. Installa **Expo Go** dall'App Store.
2. Sul computer (Node 20+):
   ```bash
   cd gym-tracker
   npm run setup   # installa e allinea all'SDK Expo più recente (quello di Expo Go)
   npx expo start
   ```
3. Inquadra il QR con la fotocamera dell'iPhone (stessa rete Wi‑Fi; altrimenti `npx expo start --tunnel`).

## Personalizzare la scheda

Modifica `src/defaultProgram.js`, oppure in app: **Programma → Importa JSON** con:

```json
{"program":[{"name":"Push","exercises":[{"name":"Panca piana","sets":4,"reps":"6-8","rest":150}]}]}
```
