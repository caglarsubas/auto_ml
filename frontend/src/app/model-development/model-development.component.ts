import { Component, OnInit } from '@angular/core';
import { Router, NavigationEnd } from '@angular/router';
import { filter } from 'rxjs/operators';

@Component({
  selector: 'app-model-development',
  templateUrl: './model-development.component.html',
  styleUrls: ['./model-development.component.css']
})
export class ModelDevelopmentComponent implements OnInit {
  currentRoute: string = '';
  menuItems = ['declaration', 'preprocessing', 'modeling', 'evaluation', 'deployment'];
  selectedPipeline: string = '';

  constructor(private router: Router) {}

  ngOnInit() {
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(() => {
      this.currentRoute = this.router.url.split('/').pop() || 'declaration';
    });
  }

  onPipelineChange(event: Event) {
    const select = event.target as HTMLSelectElement;
    this.selectedPipeline = select.value;
    // Here you can add logic to handle the pipeline change
    console.log('Selected pipeline:', this.selectedPipeline);
  }
  onStartClick() {
    if (this.selectedPipeline) {
      this.router.navigate(['/model-development/declaration']);
    }
  }
}