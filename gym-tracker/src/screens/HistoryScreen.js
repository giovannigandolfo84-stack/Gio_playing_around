import { useState } from 'react';
import { Alert, Pressable, View } from 'react-native';
import Screen from '../Screen';
import { Btn, Card, Muted, T, Title, s } from '../ui';
import { useStore } from '../store';
import { fmtDate, fmtDuration, sessionVolume } from '../theme';

export default function HistoryScreen() {
  const { state, update } = useStore();
  const [open, setOpen] = useState(null);

  return (
    <Screen>
      <Title sub={`${state.history.length} sessioni registrate`}>Storico</Title>
      {!state.history.length && <Muted>Nessun allenamento ancora. Vai su "Allena" per iniziare.</Muted>}

      {state.history.map((h) => {
        const isOpen = open === h.id;
        const dur = h.finishedAt ? new Date(h.finishedAt) - new Date(h.startedAt) : 0;
        return (
          <Pressable key={h.id} onPress={() => setOpen(isOpen ? null : h.id)}>
            <Card>
              <View style={[s.row, { justifyContent: 'space-between' }]}>
                <T style={{ fontWeight: '800', flex: 1 }}>{h.name}</T>
                <Muted>{fmtDate(h.startedAt)}</Muted>
              </View>
              <Muted style={{ marginTop: 4 }}>
                {fmtDuration(dur)} · {h.exercises.length} esercizi · {Math.round(sessionVolume(h)).toLocaleString('it-IT')} kg
              </Muted>

              {isOpen && (
                <View style={{ marginTop: 10 }}>
                  {h.exercises.map((e) => (
                    <View key={e.id} style={{ marginTop: 8 }}>
                      <T style={{ fontWeight: '700', fontSize: 15 }}>{e.name}</T>
                      <Muted>{e.sets.map((x) => `${x.kg}×${x.reps}`).join('   ')}</Muted>
                    </View>
                  ))}
                  <Btn
                    small
                    kind="danger"
                    label="Elimina sessione"
                    style={{ marginTop: 14 }}
                    onPress={() =>
                      Alert.alert('Eliminare questa sessione?', '', [
                        { text: 'No', style: 'cancel' },
                        {
                          text: 'Elimina',
                          style: 'destructive',
                          onPress: () => update((st) => ({ history: st.history.filter((x) => x.id !== h.id) })),
                        },
                      ])
                    }
                  />
                </View>
              )}
            </Card>
          </Pressable>
        );
      })}
    </Screen>
  );
}
