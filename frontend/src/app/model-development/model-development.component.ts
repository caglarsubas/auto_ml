import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd, Event as RouterEvent } from '@angular/router';
import { filter } from 'rxjs/operators';
import { SharedService } from '../services/shared.service';

@Component({
  selector: 'app-model-development',
  templateUrl: './model-development.component.html',
  styleUrls: ['./model-development.component.css']
})

export class ModelDevelopmentComponent implements OnInit {
  currentRoute: string = '';
  menuItems = ['declaration', 'preprocessing', 'modeling', 'evaluation', 'deployment'];
  selectedPipeline: string = '';
  currentStep: string = 'declaration';
  showDeclaration: boolean = false;  // Add this line
  showSteps: { [key: string]: boolean } = {
    declaration: false,
    preprocessing: false,
    modeling: false,
    evaluation: false,
    deployment: false
  };

  constructor(private router: Router, private sharedService: SharedService) {}

  ngOnInit() {
    this.router.events.pipe(
      filter((event: RouterEvent): event is NavigationEnd => event instanceof NavigationEnd)
    ).subscribe((event: NavigationEnd) => {
      const urlParts = event.urlAfterRedirects.split('/');
      this.currentStep = urlParts[urlParts.length - 1];
    });
  }

  onPipelineChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    this.selectedPipeline = select.value;
    // Here you can add logic to handle the pipeline change
    console.log('Selected pipeline:', this.selectedPipeline);
    this.sharedService.setSelectedPipeline(this.selectedPipeline);
  }

  onStartClick() {
    if (this.selectedPipeline) {
      this.sharedService.setStarted(true);
      this.router.navigate(['/model-development/declaration']);
    }
  }
}