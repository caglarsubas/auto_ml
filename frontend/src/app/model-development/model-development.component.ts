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

  constructor(private router: Router) {}

  ngOnInit() {
    this.router.events.pipe(
      filter(event => event instanceof NavigationEnd)
    ).subscribe(() => {
      this.currentRoute = this.router.url.split('/').pop() || 'declaration';
    });
  }
}