const SCHOOL_DISTRICT_LABELS: Record<string, string> = {
  '002': 'Central York',
  '004': 'Dallastown',
  '006': 'Dover',
  '008': 'Eastern York',
  '010': 'Hanover',
  '012': 'Northeastern',
  '014': 'Northern York',
  '016': 'Red Lion',
  '018': 'South Eastern',
  '020': 'South Western',
  '022': 'Southern York',
  '024': 'Spring Grove',
  '026': 'West York',
  '028': 'York City',
  '030': 'York Suburban',
  '17F': 'West Shore',
  '17G': 'West Shore',
  '17L': 'West Shore',
  '17N': 'West Shore',
}

const PROPERTY_CLASS_LABELS: Record<string, string> = {
  R: 'Residential',
  C: 'Commercial',
  I: 'Industrial',
  F: 'Farm',
  E: 'Exempt',
  A: 'Agricultural',
  U: 'Utility',
}

export function getSchoolDistrictLabel(code: string | null | undefined): string {
  if (!code) {
    return ''
  }

  return SCHOOL_DISTRICT_LABELS[code] || code
}

export function getPropertyClassLabel(code: string | null | undefined): string {
  if (!code) {
    return ''
  }

  return PROPERTY_CLASS_LABELS[code] || code
}
