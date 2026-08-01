import { Component } from '@angular/core';

export type HomeLinkStatus = 'live' | 'unavailable';
export type HomeIcon =
  | 'layers'
  | 'model'
  | 'deploy'
  | 'report'
  | 'about'
  | 'arrow'
  | 'declare'
  | 'seal'
  | 'route'
  | 'roadmap';

export interface HomeLink {
  label: string;
  route?: string;
  status: HomeLinkStatus;
}

export interface HomeSection {
  name: string;
  index: string;
  icon: HomeIcon;
  items: HomeLink[];
}

export interface EvidenceNote {
  label: string;
  body: string;
  tone: 'declared' | 'live' | 'muted';
  icon: HomeIcon;
}

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css'],
})
export class HomeComponent {
  readonly thesis = 'Declared tabular model work for regulated teams.';

  readonly evidenceNotes: EvidenceNote[] = [
    {
      label: 'Declared',
      body: 'Every modeling choice is explicit — not magic.',
      tone: 'declared',
      icon: 'seal',
    },
    {
      label: 'Live routes',
      body: 'Model Development',
      tone: 'live',
      icon: 'route',
    },
    {
      label: 'Roadmap',
      body: 'Remaining directory entries stay unavailable until shipped.',
      tone: 'muted',
      icon: 'roadmap',
    },
  ];

  readonly sections: HomeSection[] = [
    {
      name: 'Feature Store',
      index: '01',
      icon: 'layers',
      items: [
        { label: 'Feature Collection', status: 'unavailable' },
        { label: 'Feature Engineering', status: 'unavailable' },
        { label: 'Feature Monitoring', status: 'unavailable' },
      ],
    },
    {
      name: 'Model Store',
      index: '02',
      icon: 'model',
      items: [
        { label: 'Model Development', route: '/model-development', status: 'live' },
        { label: 'Model Re-Fitting', status: 'unavailable' },
        { label: 'Model Monitoring', status: 'unavailable' },
      ],
    },
    {
      name: 'Deployments',
      index: '03',
      icon: 'deploy',
      items: [
        { label: 'Deployed Artifacts', status: 'unavailable' },
        { label: 'Security Monitoring', status: 'unavailable' },
        { label: 'Performance Monitoring', status: 'unavailable' },
        { label: 'New Deployment', status: 'unavailable' },
      ],
    },
    {
      name: 'Reporting',
      index: '04',
      icon: 'report',
      items: [
        { label: 'Model Summary', status: 'unavailable' },
        { label: 'Quality Report', status: 'unavailable' },
        { label: 'Explainability', status: 'unavailable' },
        { label: 'Causality', status: 'unavailable' },
      ],
    },
    {
      name: 'About',
      index: '05',
      icon: 'about',
      items: [
        { label: 'User Guide', status: 'unavailable' },
        { label: 'White Paper', status: 'unavailable' },
        { label: 'Team & Community', status: 'unavailable' },
        { label: 'References', status: 'unavailable' },
      ],
    },
  ];
}
