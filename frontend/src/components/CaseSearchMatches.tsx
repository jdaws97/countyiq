import { Link } from 'react-router-dom'
import { useFetchJson } from '../lib/useFetchJson'
export type OrganizationSummary={owner_id:number;canonical_name:string;entity_type:string;parcel_count:number;municipality:string|null;verification_status:string|null}
type ProjectSummary={key:string;name:string;municipality:string|null;latest_date:string|null;latest_activity:string}
export default function CaseSearchMatches({query}:{query:string}) {
  const organizations=useFetchJson<{organizations:OrganizationSummary[]}>(query.length>=2?'/api/directory/organizations?limit=6&q='+encodeURIComponent(query):null)
  const projects=useFetchJson<{projects:ProjectSummary[]}>(query.length>=2?'/api/directory/projects?limit=6&q='+encodeURIComponent(query):null)
  if(!organizations.data?.organizations.length&&!projects.data?.projects.length)return null
  return <section className="case-search-matches" aria-label="Matching case files">
    {!!organizations.data?.organizations.length&&<div><h2>Organizations</h2>{organizations.data.organizations.map(item=><Link key={item.owner_id} to={'/entity/'+item.owner_id}><strong>{item.canonical_name}</strong><span>{item.parcel_count} linked parcels · {item.municipality||'County records'} · {item.verification_status==='verified'?'Identity reviewed':'Record grouping; verify relationships'}</span></Link>)}</div>}
    {!!projects.data?.projects.length&&<div><h2>Projects</h2>{projects.data.projects.map(item=><Link key={item.key} to={'/project/'+encodeURIComponent(item.key)}><strong>{item.name}</strong><span>{item.municipality} · {item.latest_date||'Date unverified'}</span><span>{item.latest_activity}</span></Link>)}</div>}
  </section>
}
