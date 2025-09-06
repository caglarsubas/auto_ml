// home.component.ts
import { Component, AfterViewInit  } from '@angular/core';
import { Router } from '@angular/router';

@Component({
  selector: 'app-home',
  templateUrl: './home.component.html',
  styleUrls: ['./home.component.css']
})

export class HomeComponent implements AfterViewInit {
  menuItems = [
    { 
      name: 'Feature Store', 
      staticIcon: 'assets/feature_store_icon_2.webp',
      gifIcon: 'assets/feature_store_rightward.gif',
      subItems: ['Feature Collection', 'Feature Engineering', 'Feature Monitoring'], 
    },
    { 
      name: 'Model Store', 
      staticIcon: 'assets/model_store_4.png',
      gifIcon: 'assets/model_store_jumps.gif',
      subItems: ['Model Development', 'Model Re-Fitting', 'Model Monitoring'] },
    { 
      name: 'Deployments', 
      staticIcon: 'assets/deploy_4.png',
      gifIcon: 'assets/deploy_4_upward.gif',
      subItems: ['Deployed Artifacts', 'Security Monitoring', 'Performance Monitoring', 'New Deployment'] },
    { 
      name: 'Reporting', 
      staticIcon: 'assets/docs_3.png',
      gifIcon: 'assets/docs_3_rotation.gif',
      subItems: ['Model Summary', 'Quality Report', 'Explainability', 'Causality'] },
    { 
      name: 'About', 
      staticIcon: 'assets/about_4.png',
      gifIcon: 'assets/about_4_zoom.gif',
      subItems: ['User Guide', 'White Paper', 'Team & Community', 'References'] }
  ];

  constructor(private router: Router) {}

  ngAfterViewInit() {
    const icons = document.querySelectorAll('.menu-icon');
    icons.forEach((icon) => {
      if (icon instanceof HTMLImageElement) {
        const container = icon.closest('.icon-container') as HTMLElement;
        if (container) {
          container.style.setProperty('--gif-src', `url('${icon.getAttribute('data-gif')}')`);
        }
      }
    });
  }

  navigateToModelDevelopment() {
    this.router.navigate(['/model-development']);
  }
}