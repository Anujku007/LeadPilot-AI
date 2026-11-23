import { Component } from 'react'

/**
 * Confine unexpected Sales Pipeline render errors to its own panel.
 * This is deliberately a UI fallback: it never sends a CRM update.
 */
export default class SalesPipelineErrorBoundary extends Component {
  constructor(props) {
    super(props)
    this.state = { error: null }
  }

  static getDerivedStateFromError(error) {
    return { error }
  }

  componentDidCatch(error, details) {
    console.error('LeadPilot Sales Pipeline rendering error:', error, details)
  }

  render() {
    if (!this.state.error) return this.props.children
    return (
      <section className="panel" role="alert" style={{ margin: 20, padding: 24, maxWidth: 800 }}>
        <h2 style={{ marginTop: 0 }}>Sales Pipeline could not display this form</h2>
        <p>Your saved meetings and CRM outcomes have not been changed by this display error.</p>
        <p style={{ marginBottom: 6, fontWeight: 700 }}>Error details:</p>
        <pre style={{ overflowWrap: 'anywhere', whiteSpace: 'pre-wrap', padding: 12, borderRadius: 8, background: '#f6f5fc' }}>
          {this.state.error.message || String(this.state.error)}
        </pre>
        <p>Copy this message and the red browser Console error if the problem repeats.</p>
        <button className="secondary-button" type="button" onClick={() => this.setState({ error: null })}>
          Retry Sales Pipeline
        </button>
      </section>
    )
  }
}
