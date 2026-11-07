import { useMemo, useState } from 'react';
import { Pressable, ScrollView, Text, View } from 'react-native';
import Screen from '../Screen';
import { Card, Muted, T, Title, s } from '../ui';
import { useStore } from '../store';
import { C, e1rm, fmtDate, sessionVolume } from '../theme';

function Bars({ points, unit }) {
  if (!points.length) return null;
  const max = Math.max(...points.map((p) => p.v));
  const min = Math.min(...points.map((p) => p.v));
  const floor = min === max ? 0 : min * 0.9;
  return (
    <View style={{ flexDirection: 'row', alignItems: 'flex-end', height: 140, gap: 4, marginTop: 12 }}>
      {points.map((p, i) => (
        <View key={i} style={{ flex: 1, alignItems: 'center', justifyContent: 'flex-end', height: '100%' }}>
          {i === points.length - 1 && (
            <Text style={{ color: C.accent, fontSize: 11, fontWeight: '700', marginBottom: 2 }}>
              {Math.round(p.v)}
              {unit}
            </Text>
          )}
          <View
            style={{
              width: '100%',
              maxWidth: 22,
              borderRadius: 4,
              backgroundColor: i === points.length - 1 ? C.accent : C.card2,
              height: `${Math.max(6, ((p.v - floor) / (max - floor || 1)) * 100)}%`,
            }}
          />
        </View>
      ))}
    </View>
  );
}

export default function ProgressScreen() {
  const { state } = useStore();
  const history = state.history;

  // Oldest -> newest stats per exercise
  const byEx = useMemo(() => {
    const m = {};
    [...history].reverse().forEach((h) =>
      h.exercises.forEach((e) => {
        const best = e.sets.reduce(
          (b, x) => {
            const kg = +x.kg || 0;
            const r = +x.reps || 0;
            return { kg: Math.max(b.kg, kg), e1: Math.max(b.e1, e1rm(kg, r)) };
          },
          { kg: 0, e1: 0 }
        );
        (m[e.name] ||= []).push({ date: h.startedAt, ...best, sets: e.sets });
      })
    );
    return m;
  }, [history]);

  const names = Object.keys(byEx).sort((a, b) => byEx[b].length - byEx[a].length);
  const [sel, setSel] = useState(null);
  const cur = sel && byEx[sel] ? sel : names[0];
  const data = cur ? byEx[cur] : [];
  const pr = data.reduce((b, d) => (d.e1 > b.e1 ? d : b), { e1: 0 });

  const volume = [...history].reverse().slice(-12).map((h) => ({ v: sessionVolume(h) }));

  if (!history.length)
    return (
      <Screen>
        <Title>Progressi</Title>
        <Muted>Completa qualche allenamento per vedere i grafici.</Muted>
      </Screen>
    );

  return (
    <Screen>
      <Title sub="Massimale stimato (Epley) e volume">Progressi</Title>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginBottom: 12 }}>
        {names.map((n) => (
          <Pressable
            key={n}
            onPress={() => setSel(n)}
            style={{
              paddingVertical: 8,
              paddingHorizontal: 12,
              borderRadius: 20,
              marginRight: 8,
              backgroundColor: n === cur ? C.accent : C.card2,
            }}
          >
            <Text style={{ color: n === cur ? C.accentText : C.text, fontWeight: '600' }}>{n}</Text>
          </Pressable>
        ))}
      </ScrollView>

      {cur && (
        <Card>
          <T style={{ fontWeight: '800', fontSize: 18 }}>{cur}</T>
          <View style={[s.row, { gap: 20, marginTop: 8 }]}>
            <View>
              <Muted>1RM stimato (PR)</Muted>
              <T style={{ fontSize: 22, fontWeight: '800', color: C.accent }}>{Math.round(pr.e1)} kg</T>
            </View>
            <View>
              <Muted>Carico max</Muted>
              <T style={{ fontSize: 22, fontWeight: '800' }}>{Math.max(...data.map((d) => d.kg))} kg</T>
            </View>
          </View>
          <Bars points={data.slice(-12).map((d) => ({ v: d.e1 }))} unit="kg" />
          <View style={{ marginTop: 12 }}>
            {[...data].reverse().slice(0, 6).map((d, i) => (
              <View key={i} style={[s.row, { justifyContent: 'space-between', marginTop: 6 }]}>
                <Muted>{fmtDate(d.date)}</Muted>
                <T style={{ fontSize: 14 }}>{d.sets.map((x) => `${x.kg}×${x.reps}`).join('  ')}</T>
              </View>
            ))}
          </View>
        </Card>
      )}

      <Card>
        <T style={{ fontWeight: '800', fontSize: 18 }}>Volume per sessione</T>
        <Muted>kg × ripetizioni, ultime 12 sessioni</Muted>
        <Bars points={volume} unit="" />
      </Card>
    </Screen>
  );
}
