import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';

describe('miniappBridge', () => {
  let originalEnv;
  let originalWx;

  beforeEach(() => {
    originalEnv = window.__wxjs_environment;
    originalWx = window.wx;
  });

  afterEach(() => {
    window.__wxjs_environment = originalEnv;
    window.wx = originalWx;
  });

  it('isInMiniapp returns false in browser', async () => {
    delete window.__wxjs_environment;
    const { isInMiniapp } = await import('../miniappBridge.js?t=1');
    expect(isInMiniapp()).toBe(false);
  });

  it('isInMiniapp returns true when __wxjs_environment is miniprogram', async () => {
    window.__wxjs_environment = 'miniprogram';
    const { isInMiniapp } = await import('../miniappBridge.js?t=2');
    expect(isInMiniapp()).toBe(true);
  });

  it('openAddRuleVoice is a no-op when not in miniapp', async () => {
    delete window.__wxjs_environment;
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=3');
    const spy = vi.fn();
    window.wx = { miniProgram: { navigateTo: spy } };
    openAddRuleVoice();
    expect(spy).not.toHaveBeenCalled();
  });

  it('openAddRuleVoice calls navigateTo when in miniapp', async () => {
    window.__wxjs_environment = 'miniprogram';
    const spy = vi.fn();
    window.wx = { miniProgram: { navigateTo: spy } };
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=4');
    openAddRuleVoice();
    expect(spy).toHaveBeenCalledWith(expect.objectContaining({ url: '/pages/add-rule/add-rule' }));
  });

  it('openAddRuleVoice invokes onStaleVersion on navigateTo fail', async () => {
    window.__wxjs_environment = 'miniprogram';
    const onStaleVersion = vi.fn();
    window.wx = {
      miniProgram: {
        navigateTo: (opts) => opts.fail && opts.fail(),
      },
    };
    const { openAddRuleVoice } = await import('../miniappBridge.js?t=5');
    openAddRuleVoice({ onStaleVersion });
    expect(onStaleVersion).toHaveBeenCalled();
  });
});
