if (process.env.NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE?.trim() === '1') {
  console.error('Production build refused: NEXT_PUBLIC_WORKSPACE_FIXTURE_MODE must not be enabled.')
  process.exit(1)
}
