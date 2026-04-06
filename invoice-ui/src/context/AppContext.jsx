import { createContext, useContext, useState } from 'react'

const AppContext = createContext(null)

export function AppProvider({ children }) {
  const [processingState, setProcessingState] = useState({
    phase: 'idle',      // idle | processing | done | approved | rejected | error
    result: null,
    error: '',
    jobId: null,
    fileName: '',
  })

  return (
    <AppContext.Provider value={{ processingState, setProcessingState }}>
      {children}
    </AppContext.Provider>
  )
}

export function useApp() {
  return useContext(AppContext)
}
