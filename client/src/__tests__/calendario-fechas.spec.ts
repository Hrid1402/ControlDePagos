import { afterEach, describe, expect, it, vi } from 'vitest'
import { hoyLima } from '@/components/calendario/fechas'

afterEach(() => vi.useRealTimers())

describe('día actual del calendario', () => {
  it('usa la fecha de Lima aunque el UTC ya cambió de día', () => {
    vi.useFakeTimers({ toFake: ['Date'] })
    vi.setSystemTime(new Date('2026-10-21T02:00:00Z'))
    expect(hoyLima()).toBe('2026-10-20')
  })
})
