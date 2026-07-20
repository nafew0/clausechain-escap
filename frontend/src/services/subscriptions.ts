import api from './api'

export async function getPlans() {
  const response = await api.get('/plans/')
  return response.data?.results ?? response.data
}

export async function getSubscription() {
  const response = await api.get('/subscription/')
  return response.data
}

export async function getUsage() {
  const response = await api.get('/subscription/usage/')
  return response.data
}

export async function cancelSubscription() {
  const response = await api.post('/subscription/cancel/')
  return response.data
}
