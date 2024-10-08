import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd, Event as RouterEvent } from '@angular/router';
import { filter } from 'rxjs/operators';
import { SharedService } from '../services/shared.service';
import { MatSelectChange } from '@angular/material/select';

interface PurifierOption {
  id: number;
  name: string;
  group?: number;
}

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
  showDeclaration: boolean = false;
  showSteps: { [key: string]: boolean } = {
    declaration: false,
    preprocessing: false,
    modeling: false,
    evaluation: false,
    deployment: false
  };
  purifierOptions: PurifierOption[] = [
    { id: 1, name: 'Column-wise duplicate drop' },
    { id: 2, name: 'Row-wise duplicate drop' },
    { id: 3, name: 'Zero-variance drop' },
    { id: 4, name: 'Perfect-correlation drop' },
    { id: 5, name: 'Corr-drop threshold = 0.95', group: 1 },
    { id: 6, name: 'Corr-drop threshold = 0.90', group: 1 },
    { id: 7, name: 'Corr-drop threshold = 0.85', group: 1 },
    { id: 8, name: 'Corr-drop threshold = 0.80', group: 1 },
    { id: 9, name: 'Corr-drop threshold = 0.75', group: 1 },
    { id: 10, name: 'Sparsity-drop threshold = 0.99', group: 2 },
    { id: 11, name: 'Sparsity-drop threshold = 0.95', group: 2 },
    { id: 12, name: 'Sparsity-drop threshold = 0.90', group: 2 },
    { id: 13, name: 'Sparsity-drop threshold = 0.85', group: 2 },
    { id: 14, name: 'Sparsity-drop threshold = 0.80', group: 2 },
    { id: 15, name: 'Sparsity-drop threshold = 0.75', group: 2 },
    { id: 16, name: 'Missing-drop threshold = 0.99', group: 3 },
    { id: 17, name: 'Missing-drop threshold = 0.95', group: 3 },
    { id: 18, name: 'Missing-drop threshold = 0.90', group: 3 },
    { id: 19, name: 'Missing-drop threshold = 0.85', group: 3 },
    { id: 20, name: 'Missing-drop threshold = 0.80', group: 3 },
    { id: 21, name: 'Missing-drop threshold = 0.75', group: 3 },
    { id: 22, name: '[Sparsity+Missing]-drop threshold = 0.99', group: 4 },
    { id: 23, name: '[Sparsity+Missing]-drop threshold = 0.95', group: 4 },
    { id: 24, name: '[Sparsity+Missing]-drop threshold = 0.90', group: 4 },
    { id: 25, name: '[Sparsity+Missing]-drop threshold = 0.85', group: 4 },
    { id: 26, name: '[Sparsity+Missing]-drop threshold = 0.80', group: 4 },
    { id: 27, name: '[Sparsity+Missing]-drop threshold = 0.75', group: 4 },
    { id: 28, name: 'Outlier-cleaning [lower-upper] quantiles = [0.01-0.99]', group: 5 },
    { id: 29, name: 'Outlier-cleaning [lower-upper] quantiles = [0.05-0.95]', group: 5 },
    { id: 30, name: 'Outlier-cleaning [lower-upper] quantiles = [0.10-0.90]', group: 5 },
  ];

  selectedOptions: PurifierOption[] = [];

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

  onSelectionChange(event: MatSelectChange): void {
    const selectedGroups = new Set(this.selectedOptions.map(option => option.group).filter(group => group !== undefined));
    
    this.selectedOptions = this.selectedOptions.filter(option => 
      !option.group || selectedGroups.has(option.group)
    );
  }

  isOptionDisabled(option: PurifierOption): boolean {
    if (!option.group) return false;

    const selectedGroups = new Set(this.selectedOptions.map(opt => opt.group).filter(group => group !== undefined));
    return selectedGroups.has(option.group) && !this.selectedOptions.includes(option);
  }
}