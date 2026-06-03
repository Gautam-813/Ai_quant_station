import { describe, it, expect, beforeEach } from 'vitest'
import { useAIAnalystStore } from '@/store/aiAnalystStore'

describe('AIAnalystStore', () => {
  beforeEach(() => {
    useAIAnalystStore.setState({
      messages: [],
      provider: 'nvidia',
      model: 'qwen/qwen3.5-122b-a10b',
      persona: 'technical_analyst',
      symbol: undefined,
      customSymbol: '',
      loadData: 'none',
      dataPeriod: '1mo',
      timeframe: '1m',
      loadedData: null,
      liveMode: false,
      feedbackSet: [],
    })
  })

  describe('initial state', () => {
    it('has correct default values', () => {
      const state = useAIAnalystStore.getState()
      expect(state.messages).toEqual([])
      expect(state.provider).toBe('nvidia')
      expect(state.model).toBe('qwen/qwen3.5-122b-a10b')
      expect(state.persona).toBe('technical_analyst')
      expect(state.symbol).toBeUndefined()
      expect(state.customSymbol).toBe('')
      expect(state.loadData).toBe('none')
      expect(state.dataPeriod).toBe('1mo')
      expect(state.timeframe).toBe('1m')
      expect(state.loadedData).toBeNull()
      expect(state.liveMode).toBe(false)
      expect(state.feedbackSet).toEqual([])
    })
  })

  describe('setMessages', () => {
    it('replaces all messages', () => {
      const msgs = [{ role: 'user', content: 'hello' }]
      useAIAnalystStore.getState().setMessages(msgs)
      expect(useAIAnalystStore.getState().messages).toEqual(msgs)
    })

    it('overwrites previous messages', () => {
      useAIAnalystStore.setState({ messages: [{ role: 'user', content: 'old' }] })
      useAIAnalystStore.getState().setMessages([{ role: 'assistant', content: 'new' }])
      expect(useAIAnalystStore.getState().messages).toHaveLength(1)
      expect(useAIAnalystStore.getState().messages[0].content).toBe('new')
    })
  })

  describe('addMessage', () => {
    it('appends a message', () => {
      useAIAnalystStore.getState().addMessage({ role: 'user', content: 'first' })
      useAIAnalystStore.getState().addMessage({ role: 'assistant', content: 'second' })
      expect(useAIAnalystStore.getState().messages).toHaveLength(2)
    })

    it('preserves existing messages', () => {
      useAIAnalystStore.setState({ messages: [{ role: 'user', content: 'existing' }] })
      useAIAnalystStore.getState().addMessage({ role: 'assistant', content: 'new' })
      expect(useAIAnalystStore.getState().messages[0].content).toBe('existing')
    })
  })

  describe('setters', () => {
    it('setSymbol updates symbol', () => {
      useAIAnalystStore.getState().setSymbol('EURUSD')
      expect(useAIAnalystStore.getState().symbol).toBe('EURUSD')
    })

    it('setCustomSymbol updates customSymbol', () => {
      useAIAnalystStore.getState().setCustomSymbol('BTCUSD')
      expect(useAIAnalystStore.getState().customSymbol).toBe('BTCUSD')
    })

    it('setTimeframe updates timeframe', () => {
      useAIAnalystStore.getState().setTimeframe('1H')
      expect(useAIAnalystStore.getState().timeframe).toBe('1H')
    })

    it('setProvider updates provider', () => {
      useAIAnalystStore.getState().setProvider('groq')
      expect(useAIAnalystStore.getState().provider).toBe('groq')
    })

    it('setModel updates model', () => {
      useAIAnalystStore.getState().setModel('llama-3.3-70b')
      expect(useAIAnalystStore.getState().model).toBe('llama-3.3-70b')
    })

    it('setPersona updates persona', () => {
      useAIAnalystStore.getState().setPersona('synthesizer')
      expect(useAIAnalystStore.getState().persona).toBe('synthesizer')
    })

    it('setLoadData updates loadData', () => {
      useAIAnalystStore.getState().setLoadData('yahoo')
      expect(useAIAnalystStore.getState().loadData).toBe('yahoo')
    })

    it('setDataPeriod updates dataPeriod', () => {
      useAIAnalystStore.getState().setDataPeriod('1w')
      expect(useAIAnalystStore.getState().dataPeriod).toBe('1w')
    })

    it('setLoadedData updates loadedData', () => {
      const info = { source: 'yahoo', symbol: 'EURUSD', startDate: '2024-01-01', endDate: '2024-12-31', candles: 5000 }
      useAIAnalystStore.getState().setLoadedData(info)
      expect(useAIAnalystStore.getState().loadedData).toEqual(info)
    })

    it('setLiveMode toggles liveMode', () => {
      useAIAnalystStore.getState().setLiveMode(true)
      expect(useAIAnalystStore.getState().liveMode).toBe(true)
      useAIAnalystStore.getState().setLiveMode(false)
      expect(useAIAnalystStore.getState().liveMode).toBe(false)
    })
  })

  describe('addFeedback', () => {
    it('adds a feedback index', () => {
      useAIAnalystStore.getState().addFeedback(0)
      expect(useAIAnalystStore.getState().feedbackSet).toEqual([0])
    })

    it('does not duplicate feedback index', () => {
      useAIAnalystStore.getState().addFeedback(1)
      useAIAnalystStore.getState().addFeedback(1)
      expect(useAIAnalystStore.getState().feedbackSet).toEqual([1])
    })

    it('accumulates multiple feedback indices', () => {
      useAIAnalystStore.getState().addFeedback(0)
      useAIAnalystStore.getState().addFeedback(2)
      useAIAnalystStore.getState().addFeedback(5)
      expect(useAIAnalystStore.getState().feedbackSet).toEqual([0, 2, 5])
    })
  })

  describe('clearMessages', () => {
    it('clears messages and feedbackSet', () => {
      useAIAnalystStore.setState({
        messages: [{ role: 'user', content: 'test' }],
        feedbackSet: [0, 1],
      })
      useAIAnalystStore.getState().clearMessages()
      expect(useAIAnalystStore.getState().messages).toEqual([])
      expect(useAIAnalystStore.getState().feedbackSet).toEqual([])
    })
  })

  describe('clearAll', () => {
    it('resets to initial state', () => {
      useAIAnalystStore.setState({
        messages: [{ role: 'user', content: 'test' }],
        provider: 'groq',
        model: 'llama-3.3-70b',
        persona: 'synthesizer',
        symbol: 'EURUSD',
        customSymbol: 'BTCUSD',
        loadData: 'yahoo',
        dataPeriod: '1w',
        timeframe: '1H',
        loadedData: { source: 'yahoo', symbol: 'EURUSD', startDate: '2024-01-01', endDate: '2024-12-31', candles: 5000 },
        liveMode: true,
        feedbackSet: [0, 1],
      })

      useAIAnalystStore.getState().clearAll()

      const state = useAIAnalystStore.getState()
      expect(state.messages).toEqual([])
      expect(state.provider).toBe('nvidia')
      expect(state.model).toBe('qwen/qwen3.5-122b-a10b')
      expect(state.persona).toBe('technical_analyst')
      expect(state.symbol).toBeUndefined()
      expect(state.customSymbol).toBe('')
      expect(state.loadData).toBe('none')
      expect(state.dataPeriod).toBe('1mo')
      expect(state.timeframe).toBe('1m')
      expect(state.loadedData).toBeNull()
      expect(state.liveMode).toBe(false)
      expect(state.feedbackSet).toEqual([])
    })
  })
})
