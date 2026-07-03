import { describe, expect, it } from 'vitest'

import { getNestedRecord, setNestedField } from './utils'

describe('plugin-config utils', () => {
  it('maps fallback general section reads to top-level config fields', () => {
    const config = {
      plugin: { enabled: true },
      rules: [{ name: 'rule-a' }, { name: 'rule-b' }],
    }

    expect(getNestedRecord(config, 'general')).toBe(config)
  })

  it('maps fallback general section writes to top-level config fields', () => {
    const config = {
      plugin: { enabled: true },
      rules: [{ name: 'rule-a' }],
    }

    const nextConfig = setNestedField(config, 'general', 'rules', [
      { name: 'rule-a' },
      { name: 'rule-b' },
    ])

    expect(nextConfig).toEqual({
      plugin: { enabled: true },
      rules: [{ name: 'rule-a' }, { name: 'rule-b' }],
    })
    expect(nextConfig).not.toHaveProperty('general')
  })

  it('keeps nested section reads and writes unchanged', () => {
    const config = {
      matching: { recent_user_message_limit: 8 },
    }

    expect(getNestedRecord(config, 'matching')).toEqual({ recent_user_message_limit: 8 })
    expect(setNestedField(config, 'matching', 'recent_user_message_limit', 4)).toEqual({
      matching: { recent_user_message_limit: 4 },
    })
  })

  it('keeps a real general section nested', () => {
    const config = {
      general: { rules: [{ name: 'nested-rule' }] },
      rules: [{ name: 'top-level-rule' }],
    }

    expect(getNestedRecord(config, 'general')).toEqual({ rules: [{ name: 'nested-rule' }] })
    expect(setNestedField(config, 'general', 'rules', [{ name: 'changed' }])).toEqual({
      general: { rules: [{ name: 'changed' }] },
      rules: [{ name: 'top-level-rule' }],
    })
  })
})
