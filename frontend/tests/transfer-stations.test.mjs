import test from 'node:test'
import assert from 'node:assert/strict'
import { resolveViaStations } from '../src/lib/journey.js'

test('manual transfer resolves through the full station dictionary without convenience data', async () => {
  const result = await resolveViaStations(['合肥南', '', 'nan chang'], async word => word==='合肥南'
    ? [{name:'合肥南',telecode:'ENH',pinyin:'hefeinan',pinyin_abbr:'hfn'}]
    : [{name:'南昌',telecode:'NCG',pinyin:'nan chang',pinyin_abbr:'nc'}])
  assert.deepEqual(result, ['ENH','NCG'])
})

test('unknown or ambiguous transfer inputs cannot silently select a different station', async () => {
  await assert.rejects(resolveViaStations(['unknown'], async () => []), /无法识别/)
  await assert.rejects(resolveViaStations(['nc'], async () => [
    {name:'南昌',telecode:'NCG',pinyin_abbr:'nc'}, {name:'南充',telecode:'NCW',pinyin_abbr:'nc'}]), /多个车站/)
})

test('dictionary resolution preserves the query cancellation signal', async () => {
  const controller = new AbortController()
  controller.abort()
  await assert.rejects(resolveViaStations(['合肥南'], async (_, signal) => {
    signal.throwIfAborted()
    return []
  }, controller.signal), {name:'AbortError'})
})
