import { ComponentFixture, TestBed } from '@angular/core/testing';
import { HttpClientTestingModule } from '@angular/common/http/testing';
import { NoopAnimationsModule } from '@angular/platform-browser/animations';
import { MatButtonModule } from '@angular/material/button';

import { DeploymentComponent } from './deployment.component';
import { SharedService } from '../services/shared.service';
import { DataService } from '../services/data.service';

describe('DeploymentComponent', () => {
  let component: DeploymentComponent;
  let fixture: ComponentFixture<DeploymentComponent>;

  beforeEach(async () => {
    await TestBed.configureTestingModule({
      declarations: [DeploymentComponent],
      imports: [
        HttpClientTestingModule,
        NoopAnimationsModule,
        MatButtonModule,
      ],
      providers: [SharedService, DataService],
    }).compileComponents();

    fixture = TestBed.createComponent(DeploymentComponent);
    component = fixture.componentInstance;
    fixture.detectChanges();
  });

  it('should create', () => {
    expect(component).toBeTruthy();
  });
});
