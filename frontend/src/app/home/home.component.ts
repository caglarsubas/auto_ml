import { Component } from '@angular/core';

export type HomeLinkStatus = 'live' | 'unavailable';

export interface HomeLink {
  label: string;
  route?: string;
  status: HomeLinkStatus;
}

export interface HomeSection {
  name: string;
  items: HomeLink[];
}

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent {
  readonly sections: HomeSection[] = [
    {
      name: 'Feature Store',
      items: [
        { label: 'Feature Collection', route: '/feature-store/collections', status: 'live' },
        { label: 'Feature Engineering', status: 'unavailable' },
        { label: 'Feature Monitoring', status: 'unavailable' },
      ],
    },
    {
      name: 'Model Store',
      items: [
        { label: 'Model Development', route: '/model-development', status: 'live' },
        { label: 'Model Re-Fitting', status: 'unavailable' },
        { label: 'Model Monitoring', status: 'unavailable' },
      ],
    },
    {
      name: 'Deployments',
      items: [
        { label: 'Deployed Artifacts', status: 'unavailable' },
        { label: 'Security Monitoring', status: 'unavailable' },
        { label: 'Performance Monitoring', status: 'unavailable' },
        { label: 'New Deployment', status: 'unavailable' },
      ],
    },
    {
      name: 'Reporting',
      items: [
        { label: 'Model Summary', status: 'unavailable' },
        { label: 'Quality Report', status: 'unavailable' },
        { label: 'Explainability', status: 'unavailable' },
        { label: 'Causality', status: 'unavailable' },
      ],
    },
    {
      name: 'About',
      items: [
        { label: 'User Guide', status: 'unavailable' },
        { label: 'White Paper', status: 'unavailable' },
        { label: 'Team & Community', status: 'unavailable' },
        { label: 'References', status: 'unavailable' },
      ],
    },
  ];
}
