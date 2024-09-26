// home.component.ts
import { Component } from '@angular/core';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})
export class HomeComponent {
  menuItems = [
    { 
      name: 'Feature Store', 
      icon: 'assets/feature_store_icon.webp',
      subItems: ['Feature Collection', 'Feature Engineering', 'Feature Monitoring'], 
    },
    { 
      name: 'Model Store', 
      icon: 'assets/model_store_4.png',
      subItems: ['Model Development', 'Model Re-Fitting', 'Model Monitoring'] },
    { 
      name: 'Deployments', 
      icon: 'assets/deploy_4.png',
      subItems: ['Deployed Artifacts', 'Security Monitoring', 'Performance Monitoring', 'New Deployment'] },
    { 
      name: 'Reporting', 
      icon: 'assets/docs_3.png',
      subItems: ['Model Summary', 'Quality Report', 'Explainability', 'Causality'] },
    { 
      name: 'About', 
      icon: 'assets/about_4.png',
      subItems: ['declar.ai', 'Team', 'References', 'Community'] }
  ];
}