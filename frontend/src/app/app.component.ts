import { Component, OnInit, Inject, PLATFORM_ID } from '@angular/core';
import { Router, NavigationEnd, Event } from '@angular/router';
import { filter } from 'rxjs/operators';
import { isPlatformBrowser } from '@angular/common';
import { AuthService } from './services/auth.service';  // Make sure to import AuthService

@Component({
  selector: 'app-root',
  templateUrl: './app.component.html',
  styleUrl: './app.component.css'
})

export class AppComponent implements OnInit {
  title = 'frontend';
  showMagnifier = false;
  magnifierX = 0;
  magnifierY = 0;
  readonly magnifierSize = 100; // Diameter of the magnifier in pixels
  isLoginPage = false;
  isHomePage = false;
  isBrowser: boolean;

  constructor(
    private router: Router,
    @Inject(PLATFORM_ID) private platformId: Object,
    private authService: AuthService  // Inject AuthService
  ) {
    this.isBrowser = isPlatformBrowser(this.platformId);
  }

  ngOnInit() {
    if (this.isBrowser) {
      this.router.events.pipe(
        filter((event: Event): event is NavigationEnd => event instanceof NavigationEnd)
      ).subscribe((event: NavigationEnd) => {
        this.isLoginPage = event.urlAfterRedirects === '/login';
        this.isHomePage = event.urlAfterRedirects.startsWith('/home');
      });
    }
  }

  updateMagnifier(event: MouseEvent) {
    if (this.isBrowser) {
      const rect = (event.target as HTMLElement).getBoundingClientRect();
      this.magnifierX = event.clientX - rect.left - this.magnifierSize / 2;
      this.magnifierY = event.clientY - rect.top - this.magnifierSize / 2;
    }
  }
  
  shouldShowFullMenu(): boolean {
    return !this.isLoginPage && !this.isHomePage;
  }

  onSignOut() {
    this.authService.logout();
    this.router.navigate(['/login']);
  }
  
}